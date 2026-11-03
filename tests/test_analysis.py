import json

from analysis import (
    load_activities,
    load_daily_stats,
    summarize_activity,
    summarize_running,
    summarize_strength,
    summarize_daily_stats,
    build_context_snapshot,
)


def test_load_activities_returns_list(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    sample = {"summary": {"activityId": "123", "activityName": "Test Run",
              "activityType": {"typeKey": "running"}, "startTimeLocal": "2026-10-15 08:00:00",
              "duration": 1800, "distance": 5000, "averageHR": 150, "maxHR": 175, "calories": 400}}
    (act_dir / "123.json").write_text(json.dumps(sample))
    result = load_activities(act_dir)
    assert len(result) == 1
    assert result[0]["summary"]["activityId"] == "123"


def test_load_activities_sorted_by_date(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    early = {"summary": {"activityId": "1", "startTimeLocal": "2026-10-01 08:00:00",
             "activityType": {"typeKey": "running"}}}
    late = {"summary": {"activityId": "2", "startTimeLocal": "2026-10-15 08:00:00",
            "activityType": {"typeKey": "running"}}}
    (act_dir / "1.json").write_text(json.dumps(early))
    (act_dir / "2.json").write_text(json.dumps(late))
    result = load_activities(act_dir)
    assert result[0]["summary"]["activityId"] == "1"
    assert result[1]["summary"]["activityId"] == "2"


def test_load_activities_empty_dir(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    result = load_activities(act_dir)
    assert result == []


def test_summarize_running_includes_pace_and_hr():
    activity = {"summary": {"activityName": "Carrera", "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-10-15 08:00:00", "duration": 1800, "distance": 5000,
                "averageHR": 155, "maxHR": 182, "calories": 350},
                "hr_zones": [{"zoneNumber": 1, "secsInZone": 200, "zoneLowBoundary": 100}],
                "splits": {"lapDTOs": [{"distance": 1000, "duration": 360}]}, "laps": {}}
    result = summarize_running(activity)
    assert "5.0 km" in result or "5,0 km" in result
    assert "min/km" in result
    assert "155" in result


def test_summarize_strength_includes_exercises():
    activity = {"summary": {"activityName": "Fuerza", "activityType": {"typeKey": "strength_training"},
                "startTimeLocal": "2026-10-15 09:00:00", "duration": 1800, "calories": 200,
                "averageHR": 110, "maxHR": 140},
                "exercise_sets": {"exerciseSets": [
                    {"exerciseName": "BENCH_PRESS", "repetitionCount": 10, "weight": 60, "setType": "ACTIVE"},
                    {"exerciseName": "BENCH_PRESS", "repetitionCount": 8, "weight": 65, "setType": "ACTIVE"}
                ]}, "hr_zones": [], "splits": {}, "laps": {}}
    result = summarize_strength(activity)
    assert "Fuerza" in result
    assert "BENCH_PRESS" in result or "bench" in result.lower()


def test_summarize_activity_dispatches_by_type():
    running = {"summary": {"activityType": {"typeKey": "running"}, "activityName": "Run",
               "startTimeLocal": "2026-10-15 08:00:00", "duration": 1800, "distance": 5000,
               "averageHR": 150, "maxHR": 170, "calories": 300},
               "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    result = summarize_activity(running)
    assert "km" in result


def test_summarize_activity_missing_hr():
    activity = {"summary": {"activityType": {"typeKey": "running"}, "activityName": "Run",
                "startTimeLocal": "2026-10-15 08:00:00", "duration": 1800, "distance": 5000,
                "averageHR": None, "maxHR": None, "calories": 300},
                "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    result = summarize_activity(activity)
    assert isinstance(result, str)


def test_summarize_daily_stats_includes_key_metrics():
    stats = {
        "stats": {"restingHeartRate": 48, "totalSteps": 5000, "averageStressLevel": 25,
                   "bodyBatteryHighestValue": 90, "bodyBatteryLowestValue": 15},
        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 28800,
                  "sleepScores": {"overall": {"value": 72, "qualifierKey": "GOOD"},
                                  "deepPercentage": {"value": 20, "qualifierKey": "GOOD"},
                                  "remPercentage": {"value": 25, "qualifierKey": "GOOD"}}}},
        "training_readiness": [{"score": 65, "level": "MODERATE",
                                "sleepScoreFactorPercent": 50, "recoveryTimeFactorPercent": 80}],
        "hrv": {"hrvSummary": {"weeklyAvg": 60, "lastNightAvg": 55, "status": "BALANCED"}}
    }
    result = summarize_daily_stats(stats, "2026-10-15")
    assert "48" in result
    assert "72" in result
    assert "65" in result


def test_summarize_daily_stats_missing_sleep():
    stats = {"stats": {"restingHeartRate": 50, "totalSteps": 3000},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-10-15")
    assert "50" in result
    assert isinstance(result, str)


def test_build_context_snapshot_combines_all(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    activity = {"summary": {"activityId": "1", "activityName": "Carrera",
                "activityType": {"typeKey": "running"}, "startTimeLocal": "2026-10-15 08:00:00",
                "duration": 1800, "distance": 5000, "averageHR": 155, "maxHR": 175, "calories": 350},
                "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    (act_dir / "1.json").write_text(json.dumps(activity))
    day_stats = {"stats": {"restingHeartRate": 48, "totalSteps": 5000},
                 "sleep": {}, "training_readiness": [], "hrv": {}}
    (stats_dir / "2026-10-15.json").write_text(json.dumps(day_stats))
    result = build_context_snapshot(act_dir, stats_dir, days=30)
    assert "Carrera" in result
    assert "48" in result
    assert len(result) > 100
