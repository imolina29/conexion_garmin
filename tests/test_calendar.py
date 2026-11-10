from datetime import date, timedelta

from calendar_server import generate_ics, parse_plan_json, plan_start_date


SAMPLE_PLAN = {
    "sessions": [
        {
            "weekday": 0,
            "time": "18:00",
            "duration_minutes": 90,
            "title": "Pecho + Cardio",
            "description": "Press banca 3x12, aperturas 3x10, caminadora 20min",
        },
        {
            "weekday": 2,
            "time": "18:00",
            "duration_minutes": 75,
            "title": "Espalda + Core",
            "description": "Jalón al pecho 3x12, remo 3x10, plancha 3x45s",
        },
        {
            "weekday": 5,
            "time": "07:00",
            "duration_minutes": 45,
            "title": "Carrera 5K",
            "description": "Carrera continua zona 2-3, 5km",
        },
    ],
    "valid_from": "2026-11-16",
    "weeks": 4,
    "created_at": "2026-11-10T12:00:00",
}


def test_generate_ics_produces_valid_calendar():
    ics = generate_ics(SAMPLE_PLAN)
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in ics
    assert ics.count("BEGIN:VEVENT") == 3
    assert ics.count("END:VEVENT") == 3


def test_generate_ics_contains_event_details():
    ics = generate_ics(SAMPLE_PLAN)
    assert "Pecho + Cardio" in ics
    assert "Espalda + Core" in ics
    assert "Carrera 5K" in ics
    assert "RRULE:FREQ=WEEKLY;COUNT=4" in ics


def test_generate_ics_correct_dates():
    ics = generate_ics(SAMPLE_PLAN)
    # 2026-11-16 is a Monday (weekday 0)
    assert "DTSTART:20261116T180000" in ics
    # Wednesday (weekday 2) = 2026-11-18
    assert "DTSTART:20261118T180000" in ics
    # Saturday (weekday 5) = 2026-11-21
    assert "DTSTART:20261121T070000" in ics


def test_generate_ics_duration():
    ics = generate_ics(SAMPLE_PLAN)
    # Monday 18:00 + 90min = 19:30
    assert "DTEND:20261116T193000" in ics
    # Wednesday 18:00 + 75min = 19:15
    assert "DTEND:20261118T191500" in ics


def test_generate_ics_with_user_name():
    ics = generate_ics(SAMPLE_PLAN, user_name="Ivan")
    assert "Ivan" in ics


def test_generate_ics_empty_plan():
    ics = generate_ics({"sessions": [], "weeks": 4})
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" not in ics


def testparse_plan_json_valid():
    text = """Aquí está tu plan:
```json
{"sessions": [{"weekday": 0, "time": "18:00", "duration_minutes": 60, "title": "Gym"}], "weeks": 4}
```
"""
    result = parse_plan_json(text)
    assert result is not None
    assert len(result["sessions"]) == 1
    assert result["weeks"] == 4


def testparse_plan_json_invalid():
    assert parse_plan_json("no json here") is None
    assert parse_plan_json("```json\n{invalid}\n```") is None


def test_plan_start_date_is_current_week_monday():
    result = plan_start_date()
    d = date.fromisoformat(result)
    assert d.weekday() == 0
    assert d <= date.today()
    assert (date.today() - d).days < 7
