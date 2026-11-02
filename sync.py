#!/usr/bin/env python3
"""Syncs training data from Garmin Connect to local JSON files."""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectConnectionError

DATA_DIR = Path(__file__).parent / "data"
RAW_DIR = DATA_DIR / "raw"
ACTIVITIES_DIR = RAW_DIR / "activities"
STATS_DIR = RAW_DIR / "stats"
LAST_SYNC_FILE = DATA_DIR / ".last_sync"
TOKEN_STORE = DATA_DIR / ".garmin_session"

STRENGTH_TYPES = {"strength_training", "indoor_cardio"}
RUNNING_TYPES = {"running", "treadmill_running", "trail_running"}

MAX_RETRIES = 3
RETRY_DELAY = 2


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def api_call_with_retry(func, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except (GarminConnectConnectionError, Exception) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            error_name = type(e).__name__
            print(f"  Reintentando ({attempt + 1}/{MAX_RETRIES}) tras {error_name}...")
            time.sleep(RETRY_DELAY * (attempt + 1))


def create_client() -> Garmin:
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        print("Error: GARMIN_EMAIL y GARMIN_PASSWORD deben estar en .env")
        sys.exit(1)

    client = Garmin(email, password)
    token_path = str(TOKEN_STORE)

    try:
        client.login(tokenstore=token_path)
    except Exception:
        print("Token expirado o no existe, haciendo login completo...")
        try:
            client.login(tokenstore=token_path)
        except Exception as e:
            print(f"Error de autenticación: {e}")
            sys.exit(1)

    return client


def load_last_sync() -> datetime | None:
    if LAST_SYNC_FILE.exists():
        text = LAST_SYNC_FILE.read_text().strip()
        if text:
            return datetime.fromisoformat(text)
    return None


def save_last_sync() -> None:
    LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=LAST_SYNC_FILE.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(datetime.now(datetime.timezone.utc).isoformat())
    os.replace(tmp, LAST_SYNC_FILE)


def get_activity_type_key(activity: dict) -> str:
    activity_type = activity.get("activityType", {})
    return activity_type.get("typeKey", "unknown")


def fetch_activity_details(client: Garmin, activity_id: str, type_key: str) -> dict:
    result = {"summary": {}, "details": {}, "exercise_sets": {}, "splits": {}, "hr_zones": {}, "laps": {}}

    result["details"] = api_call_with_retry(client.get_activity, activity_id)

    try:
        result["hr_zones"] = api_call_with_retry(client.get_activity_hr_in_timezones, activity_id)
    except Exception:
        pass

    try:
        result["laps"] = api_call_with_retry(client.get_activity_laps, activity_id)
    except Exception:
        pass

    if type_key in STRENGTH_TYPES:
        try:
            result["exercise_sets"] = api_call_with_retry(client.get_activity_exercise_sets, activity_id)
        except Exception:
            pass

    if type_key in RUNNING_TYPES:
        try:
            result["splits"] = api_call_with_retry(client.get_activity_splits, activity_id)
        except Exception:
            pass

    return result


def sync_activities(client: Garmin, start_date: str, end_date: str) -> int:
    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Buscando actividades del {start_date} al {end_date}...")
    activities = api_call_with_retry(client.get_activities_by_date, start_date, end_date)

    if not activities:
        print("  No se encontraron actividades en el rango.")
        return 0

    new_count = 0
    for activity in activities:
        activity_id = str(activity.get("activityId"))
        file_path = ACTIVITIES_DIR / f"{activity_id}.json"

        if file_path.exists():
            continue

        type_key = get_activity_type_key(activity)
        print(f"  Descargando: {activity.get('activityName', 'Sin nombre')} ({type_key}) - {activity_id}")

        details = fetch_activity_details(client, activity_id, type_key)
        details["summary"] = activity

        atomic_write_json(file_path, details)
        new_count += 1
        time.sleep(0.5)

    return new_count


def sync_daily_stats(client: Garmin, start_date: str, end_date: str) -> int:
    STATS_DIR.mkdir(parents=True, exist_ok=True)

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    today = date.today()
    new_count = 0

    current = start
    while current <= end:
        date_str = current.isoformat()
        file_path = STATS_DIR / f"{date_str}.json"

        if file_path.exists() and current != today:
            current += timedelta(days=1)
            continue

        print(f"  Stats: {date_str}")
        data = {}

        try:
            data["stats"] = api_call_with_retry(client.get_stats, date_str)
        except Exception:
            data["stats"] = {}

        try:
            data["sleep"] = api_call_with_retry(client.get_daily_sleep, date_str)
        except Exception:
            data["sleep"] = {}

        try:
            data["training_readiness"] = api_call_with_retry(client.get_training_readiness, date_str)
        except Exception:
            data["training_readiness"] = []

        try:
            data["hrv"] = api_call_with_retry(client.get_hrv_data, date_str)
        except Exception:
            data["hrv"] = {}

        atomic_write_json(file_path, data)
        new_count += 1
        current += timedelta(days=1)
        time.sleep(0.3)

    return new_count


def main():
    parser = argparse.ArgumentParser(description="Sincroniza datos de Garmin Connect")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=None, help="Sincronizar últimos N días")
    group.add_argument("--new", action="store_true", help="Sincronizar desde última sincronización")
    group.add_argument("--today", action="store_true", help="Sincronizar solo hoy")
    args = parser.parse_args()

    if args.today:
        start_date = date.today().isoformat()
        end_date = start_date
    elif args.new:
        last = load_last_sync()
        if last:
            start_date = last.date().isoformat()
        else:
            start_date = (date.today() - timedelta(days=30)).isoformat()
            print("Sin sincronización previa, descargando últimos 30 días...")
        end_date = date.today().isoformat()
    else:
        days = args.days or 30
        start_date = (date.today() - timedelta(days=days)).isoformat()
        end_date = date.today().isoformat()

    print(f"=== Sincronización Garmin Connect ===")
    print(f"Rango: {start_date} → {end_date}")
    print()

    client = create_client()
    print("Autenticación exitosa.\n")

    activity_count = sync_activities(client, start_date, end_date)
    print(f"\nActividades nuevas: {activity_count}")

    stats_count = sync_daily_stats(client, start_date, end_date)
    print(f"Días de estadísticas: {stats_count}")

    save_last_sync()
    print(f"\nSincronización completa.")


if __name__ == "__main__":
    main()
