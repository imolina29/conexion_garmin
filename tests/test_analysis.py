import json
from datetime import date

from analysis import (
    load_activities,
    load_daily_stats,
    summarize_activity,
    summarize_daily_stats,
    summarize_performance_metrics,
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


def test_summarize_activity_running_shows_distance_and_pace():
    activity = {"summary": {"activityName": "Carrera", "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-10-15 08:00:00", "duration": 1800, "distance": 5000,
                "averageHR": 155, "maxHR": 182, "calories": 350,
                "elevationGain": 50, "vO2MaxValue": 42.0,
                "activityTrainingLoad": 85.0, "aerobicTrainingEffect": 3.5},
                "hr_zones": [{"zoneNumber": 1, "secsInZone": 200, "zoneLowBoundary": 100}],
                "splits": {"lapDTOs": [{"distance": 1000, "duration": 360}]}, "laps": {}}
    result = summarize_activity(activity)
    assert "5.0 km" in result
    assert "min/km" in result
    assert "155" in result
    assert "42" in result
    assert "50" in result


def test_summarize_activity_strength_shows_sets():
    activity = {"summary": {"activityName": "Fuerza", "activityType": {"typeKey": "strength_training"},
                "startTimeLocal": "2026-10-15 09:00:00", "duration": 1800, "calories": 200,
                "totalSets": 10, "totalReps": 120, "averageHR": 110, "maxHR": 140},
                "exercise_sets": {"exerciseSets": [
                    {"exerciseName": "BENCH_PRESS", "repetitionCount": 10, "weight": 60, "setType": "ACTIVE"},
                    {"exerciseName": "BENCH_PRESS", "repetitionCount": 8, "weight": 65, "setType": "ACTIVE"}
                ]}, "hr_zones": [], "splits": {}, "laps": {}}
    result = summarize_activity(activity)
    assert "Fuerza" in result
    assert "10" in result
    assert "120" in result
    assert "BENCH_PRESS" in result


def test_summarize_activity_unknown_type_still_useful():
    activity = {"summary": {"activityName": "Yoga", "activityType": {"typeKey": "yoga"},
                "startTimeLocal": "2026-10-15 07:00:00", "duration": 3600,
                "averageHR": 85, "maxHR": 110, "calories": 150,
                "aerobicTrainingEffect": 1.2},
                "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    result = summarize_activity(activity)
    assert "Yoga" in result
    assert "60" in result
    assert "85" in result
    assert "150" in result


def test_summarize_activity_hiking_shows_elevation():
    activity = {"summary": {"activityName": "Hiking", "activityType": {"typeKey": "hiking"},
                "startTimeLocal": "2026-10-15 06:00:00", "duration": 7200, "distance": 8000,
                "averageHR": 120, "maxHR": 155, "calories": 600,
                "elevationGain": 450, "elevationLoss": 300},
                "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    result = summarize_activity(activity)
    assert "8.0 km" in result
    assert "450" in result


def test_summarize_activity_missing_hr():
    activity = {"summary": {"activityType": {"typeKey": "running"}, "activityName": "Run",
                "startTimeLocal": "2026-10-15 08:00:00", "duration": 1800, "distance": 5000,
                "averageHR": None, "maxHR": None, "calories": 300},
                "hr_zones": [], "splits": {}, "laps": {}, "exercise_sets": {}}
    result = summarize_activity(activity)
    assert isinstance(result, str)
    assert "FC" not in result


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
    result = build_context_snapshot(act_dir, stats_dir, days=30, today=date(2026, 10, 20))
    assert "Carrera" in result
    assert "48" in result
    assert len(result) > 100


def test_summarize_daily_stats_today_omits_steps():
    """Steps for the current day should be omitted entirely — they're meaningless early in the day."""
    stats = {"stats": {"totalSteps": 44, "dailyStepGoal": 5000},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-04", today=date(2026, 11, 4))
    assert "pasos" not in result.lower()
    assert "44" not in result
    assert "5,000" not in result and "5000" not in result


def test_summarize_daily_stats_past_day_not_partial():
    """Steps for a past day should NOT be marked as partial."""
    stats = {"stats": {"totalSteps": 8000, "dailyStepGoal": 5000},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-03", today=date(2026, 11, 4))
    assert "parcial" not in result.lower()
    assert "8,000" in result


def test_summarize_daily_stats_includes_step_goal():
    """Step goal from Garmin should be included in the output."""
    stats = {"stats": {"totalSteps": 5000, "dailyStepGoal": 7500},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-03", today=date(2026, 11, 4))
    assert "7,500" in result or "7500" in result


def test_summarize_daily_stats_no_today_param_backward_compat():
    """Without today param, function works as before (no partial marker)."""
    stats = {"stats": {"totalSteps": 80},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-04")
    assert "parcial" not in result.lower()
    assert "80" in result


def test_today_uses_bb_most_recent():
    """Today should show bodyBatteryMostRecentValue, not 0→0 high/low."""
    stats = {"stats": {"bodyBatteryHighestValue": 0, "bodyBatteryLowestValue": 0,
                        "bodyBatteryMostRecentValue": 72, "bodyBatteryAtWakeTime": 85},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-04", today=date(2026, 11, 4))
    assert "72" in result
    assert "0 →" not in result


def test_today_omits_meaningless_stress():
    """Stress average at 7am is meaningless — omit for today."""
    stats = {"stats": {"averageStressLevel": 2},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-04", today=date(2026, 11, 4))
    assert "estrés" not in result.lower()


def test_past_day_shows_full_bb_range():
    """Past days should show the full low→high BB range."""
    stats = {"stats": {"bodyBatteryHighestValue": 90, "bodyBatteryLowestValue": 15},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-03", today=date(2026, 11, 4))
    assert "15 → 90" in result


def test_daily_stats_includes_spo2():
    """SpO2 data should be included when available."""
    stats = {"stats": {"averageSpo2": 95.0, "lowestSpo2": 89},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-03")
    assert "95" in result
    assert "89" in result


def test_daily_stats_includes_intensity_minutes():
    """Intensity minutes should be shown when available."""
    stats = {"stats": {"moderateIntensityMinutes": 15, "vigorousIntensityMinutes": 25},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-11-03")
    assert "15" in result
    assert "25" in result


def test_snapshot_dynamic_sport_breakdown(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    for i, sport in enumerate(["hiking", "swimming", "hiking"]):
        activity = {"summary": {"activityId": str(i), "activityName": sport.title(),
                    "activityType": {"typeKey": sport}, "startTimeLocal": f"2026-10-{15+i} 08:00:00",
                    "duration": 1800, "distance": 5000}}
        (act_dir / f"{i}.json").write_text(json.dumps(activity))
    result = build_context_snapshot(act_dir, stats_dir, days=30, today=date(2026, 10, 20))
    assert "hiking" in result.lower()
    assert "swimming" in result.lower()
    assert "carrera" not in result
    assert "fuerza" not in result


def test_summarize_performance_metrics_vo2max():
    perf = {
        "max_metrics": {"generic": [{"vo2MaxPreciseValue": 42.5}]},
        "training_status": {"currentTrainingStatus": "PRODUCTIVE"},
        "race_predictions": [{"raceTime": {"5k": 1500, "10k": 3200}}],
    }
    result = summarize_performance_metrics(perf)
    assert "42.5" in result
    assert "PRODUCTIVE" in result


def test_summarize_performance_metrics_empty():
    result = summarize_performance_metrics({})
    assert result == ""


def test_summarize_performance_metrics_partial():
    perf = {"endurance_score": {"overallScore": 68}}
    result = summarize_performance_metrics(perf)
    assert "68" in result


def test_snapshot_includes_sport_profile(tmp_path):
    act_dir = tmp_path / "activities"
    act_dir.mkdir()
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    for i in range(5):
        a = {"summary": {"activityId": str(i), "activityName": "Run",
             "activityType": {"typeKey": "running"}, "startTimeLocal": f"2026-10-{10+i} 08:00:00",
             "duration": 1800, "distance": 5000, "averageHR": 155}}
        (act_dir / f"{i}.json").write_text(json.dumps(a))
    for i in range(3):
        a = {"summary": {"activityId": str(10+i), "activityName": "Fuerza",
             "activityType": {"typeKey": "strength_training"}, "startTimeLocal": f"2026-10-{15+i} 09:00:00",
             "duration": 2400, "totalSets": 12, "totalReps": 100}}
        (act_dir / f"{10+i}.json").write_text(json.dumps(a))
    result = build_context_snapshot(act_dir, stats_dir, days=30, today=date(2026, 10, 25))
    assert "PERFIL DEPORTIVO" in result
    assert "running" in result.lower()
    assert "strength" in result.lower()
