from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import main
from weather import evaluate

start = datetime(2030, 5, 2, 10, 30)
limits = dict(starts=start, minutes=90, low=5, high=25, rain=30, wind=20)
hour = start.replace(minute=0)
hours = {hour + timedelta(hours=i): [15, 80 if i == 1 else 10, 12] for i in range(5)}


def test_entire_duration_must_fit():
    assert evaluate(limits, hours, hour)["suggestion"] == hour + timedelta(hours=2)


def test_missing_second_hour():
    assert evaluate(limits, {hour: [15,10,12]}, hour)["hours"] == []


def test_no_suitable_window():
    assert evaluate(dict(limits, wind=5), hours, hour)["suggestion"] is None


def test_move_persists_once(monkeypatch):
    monkeypatch.setattr(main, "now", lambda: hour)
    monkeypatch.setattr(main, "forecast", lambda city, day: hours)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        client.get("/api/session")
        user = client.cookies["calendar"]
        try:
            body = dict(limits, starts=start.isoformat(), city="Москва", sport="Бег")
            created = client.post("/api/workouts", json=body)
            assert created.status_code == 201
            path = "/api/workouts/"+str(created.json()["id"])
            suggested = client.get(path+"/forecast").json()["suggestion"]
            assert suggested == "2030-05-02T12:00:00"
            move = dict(previous=start.isoformat(), replacement=suggested)
            assert client.post(path+"/move",json=move).status_code == 200
            assert client.post(path+"/move",json=move).status_code == 409
            assert client.get("/api/workouts").json()[0]["starts"] == suggested
            assert client.get(path+"/history").json() == [move]
            assert client.put(path+"/status?value=done").json()["status"] == "done"
            client.cookies.clear()
            client.get("/api/session")
            assert client.get(path+"/history").status_code == 404
        finally:
            with main.connect() as db:
                db.execute("DELETE FROM workouts WHERE owner=%s",(user,))
