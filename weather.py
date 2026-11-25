from datetime import datetime, timedelta
from functools import lru_cache
import time

import httpx
from fastapi import HTTPException

# All supported cities use Moscow time (UTC+3) throughout the year.
CITIES = {"Санкт-Петербург": (59.94, 30.31), "Москва": (55.75, 37.62),
          "Казань": (55.79, 49.12), "Сочи": (43.59, 39.72)}
FIELDS = ["temperature_2m", "precipitation_probability", "wind_speed_10m"]


@lru_cache(maxsize=128)
def fetch(city, day, bucket):
    lat, lon = CITIES[city]
    try:
        response = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=5,
            params=dict(latitude=lat, longitude=lon, hourly=",".join(FIELDS),
                        timezone="Europe/Moscow", start_date=day, end_date=day))
        response.raise_for_status()
        data = response.json()["hourly"]
        return {datetime.fromisoformat(t): values for t, *values in
                zip(data["time"], *(data[k] for k in FIELDS), strict=True)
                if all(isinstance(v, (float, int)) for v in values)}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Прогноз временно недоступен") from exc


def forecast(city, day):
    return fetch(city, day.isoformat(), int(time.time() // 900))


def evaluate(row, hours, now):
    start = row["starts"]
    duration = timedelta(minutes=row["minutes"])

    def samples(at):
        cursor = at.replace(minute=0)
        result = []
        while cursor < at + duration:
            if cursor not in hours:
                return []
            result.append(hours[cursor])
            cursor += timedelta(hours=1)
        return result

    def suitable(values):
        return bool(values) and all(row["low"] <= t <= row["high"] and
            rain <= row["rain"] and wind <= row["wind"] for t, rain, wind in values)

    original = samples(start)
    result = dict(hours=original, suitable=suitable(original), suggestion=None)
    if original and not result["suitable"]:
        options = [t for t in hours if t.date() == start.date() and t >= now
                   and (t + duration - timedelta(seconds=1)).date() == start.date()
                   and suitable(samples(t))]
        if options:
            result["suggestion"] = min(options, key=lambda t: (abs(t-start), t))
    return result
