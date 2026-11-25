import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather import CITIES, evaluate, forecast

ROOT = Path(__file__).parent


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


@asynccontextmanager
async def lifespan(app):
    with connect() as db:
        db.execute((ROOT / "schema.sql").read_text())
    yield


app = FastAPI(title="Календарь тренировок", lifespan=lifespan)


def now():
    return datetime.now(timezone(timedelta(hours=3))).replace(tzinfo=None)


def owner(calendar: UUID | None = Cookie(None)):
    if calendar is None:
        raise HTTPException(401, "Откройте свой календарь")
    return calendar


Owner = Annotated[UUID, Depends(owner)]


@app.get("/api/session")
def session(response: Response, calendar: UUID | None = Cookie(None)):
    if calendar is None:
        response.set_cookie("calendar", str(uuid4()), httponly=True, samesite="strict",
                            max_age=60*60*24*365)
    response.headers["Cache-Control"] = "no-store"
    return {"cities": list(CITIES), "today": now().date()}


class Workout(BaseModel):
    city: str
    sport: str = Field(min_length=1, max_length=60)
    starts: datetime
    minutes: int = Field(ge=15, le=240)
    low: float = Field(ge=-80, le=60)
    high: float = Field(ge=-80, le=60)
    rain: int = Field(ge=0, le=100)
    wind: float = Field(ge=0, le=250)


@app.post("/api/workouts", status_code=201)
def create(data: Workout, user: Owner):
    start = data.starts
    if data.city not in CITIES or data.low > data.high or not data.sport.strip():
        raise HTTPException(422, "Проверьте город, вид тренировки и диапазон температуры")
    if (start.tzinfo or start.second or start.microsecond or start <= now()
        or start.date() > now().date() + timedelta(days=6)
        or (start + timedelta(minutes=data.minutes, seconds=-1)).date() != start.date()):
        raise HTTPException(422, "Выберите будущее время в ближайшие семь дней до полуночи")
    with connect() as db:
        return db.execute("""INSERT INTO workouts(owner,city,sport,starts,minutes,low,high,rain,wind)
            VALUES (%(owner)s,%(city)s,%(sport)s,%(starts)s,%(minutes)s,%(low)s,%(high)s,%(rain)s,%(wind)s)
            RETURNING id""", dict(owner=user, **data.model_dump())).fetchone()


@app.get("/api/workouts")
def calendar(user: Owner):
    with connect() as db:
        return db.execute("""SELECT id,city,sport,starts,minutes,status FROM workouts
            WHERE owner=%s ORDER BY starts DESC,id DESC""", (user,)).fetchall()


def get_row(db, user, wid, lock=False):
    sql = "SELECT * FROM workouts WHERE owner=%s AND id=%s"
    row = db.execute(sql + (" FOR UPDATE" if lock else ""), (user, wid)).fetchone()
    if not row:
        raise HTTPException(404, "Тренировка не найдена")
    return row


def advice(row):
    return evaluate(row, forecast(row["city"], row["starts"].date()), now())


@app.get("/api/workouts/{wid}/forecast")
def preview(wid: int, user: Owner):
    with connect() as db:
        row = get_row(db, user, wid)
    return advice(row)


class Move(BaseModel):
    previous: datetime
    replacement: datetime


@app.post("/api/workouts/{wid}/move")
def move(wid: int, data: Move, user: Owner):
    with connect() as db:
        row = get_row(db, user, wid, lock=True)
        if (row["status"] != "planned" or row["starts"] != data.previous
            or advice(row)["suggestion"] != data.replacement):
            raise HTTPException(409, "Предложение изменилось. Обновите прогноз")
        db.execute("UPDATE workouts SET starts=%s WHERE id=%s", (data.replacement, wid))
        db.execute("INSERT INTO moves(workout,previous,replacement) VALUES (%s,%s,%s)",
                   (wid, data.previous, data.replacement))
    return {"starts": data.replacement}


@app.get("/api/workouts/{wid}/history")
def history(wid: int, user: Owner):
    with connect() as db:
        get_row(db, user, wid)
        return db.execute("SELECT previous,replacement FROM moves WHERE workout=%s ORDER BY id",
                          (wid,)).fetchall()


@app.put("/api/workouts/{wid}/status")
def status(wid: int, value: Literal["done","cancelled"], user: Owner):
    with connect() as db:
        row = get_row(db, user, wid, lock=True)
        if row["status"] not in ("planned", value):
            raise HTTPException(409, "Тренировка уже закрыта")
        db.execute("UPDATE workouts SET status=%s WHERE id=%s", (value, wid))
    return {"status": value}


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="ui")
