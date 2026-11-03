"""Reads Garmin JSON data and produces human-readable Spanish summaries."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

RUNNING_TYPES = {"running", "treadmill_running", "trail_running"}
STRENGTH_TYPES = {"strength_training", "indoor_cardio"}


def load_activities(activities_dir: Path) -> list[dict]:
    if not activities_dir.exists():
        return []
    files = sorted(activities_dir.glob("*.json"))
    activities = []
    for f in files:
        data = json.loads(f.read_text())
        activities.append(data)
    activities.sort(key=lambda a: a.get("summary", {}).get("startTimeLocal", ""))
    return activities


def load_daily_stats(stats_dir: Path) -> list[dict]:
    if not stats_dir.exists():
        return []
    files = sorted(stats_dir.glob("*.json"))
    result = []
    for f in files:
        data = json.loads(f.read_text())
        data["_date"] = f.stem
        result.append(data)
    return result


def summarize_running(activity: dict) -> str:
    s = activity.get("summary", {})
    name = s.get("activityName", "Actividad")
    date_str = (s.get("startTimeLocal") or "")[:10]
    duration_s = s.get("duration", 0) or 0
    duration_min = round(duration_s / 60, 1)
    distance_m = s.get("distance", 0) or 0
    distance_km = round(distance_m / 1000, 1)
    avg_hr = s.get("averageHR")
    max_hr = s.get("maxHR")
    calories = s.get("calories", 0)

    lines = [f"{date_str} — {name}"]
    lines.append(f"  Distancia: {distance_km} km | Duración: {duration_min} min")

    if distance_km > 0 and duration_min > 0:
        pace = duration_min / distance_km
        pace_min = int(pace)
        pace_sec = int((pace % 1) * 60)
        lines.append(f"  Ritmo: {pace_min}:{pace_sec:02d} min/km")

    if avg_hr is not None:
        hr_text = f"  FC: avg {int(avg_hr)}"
        if max_hr is not None:
            hr_text += f" | max {int(max_hr)}"
        lines.append(hr_text)

    hr_zones = activity.get("hr_zones") or []
    if hr_zones:
        zone_parts = []
        for z in hr_zones:
            zn = z.get("zoneNumber", "?")
            secs = z.get("secsInZone", 0)
            if secs > 0:
                zone_parts.append(f"Z{zn}: {round(secs / 60, 1)} min")
        if zone_parts:
            lines.append(f"  Zonas FC: {', '.join(zone_parts)}")

    splits = activity.get("splits", {})
    laps = splits.get("lapDTOs", [])
    if laps:
        split_texts = []
        for i, lap in enumerate(laps, 1):
            lap_dist = (lap.get("distance") or 0) / 1000
            lap_dur = (lap.get("duration") or 0) / 60
            if lap_dist > 0:
                lap_pace = lap_dur / lap_dist
                lp_min = int(lap_pace)
                lp_sec = int((lap_pace % 1) * 60)
                split_texts.append(f"km{i}: {lp_min}:{lp_sec:02d}")
        if split_texts:
            lines.append(f"  Splits: {', '.join(split_texts)}")

    if calories:
        lines.append(f"  Calorías: {int(calories)}")

    return "\n".join(lines)


def summarize_strength(activity: dict) -> str:
    s = activity.get("summary", {})
    name = s.get("activityName", "Actividad")
    date_str = (s.get("startTimeLocal") or "")[:10]
    duration_s = s.get("duration", 0) or 0
    duration_min = round(duration_s / 60, 1)
    avg_hr = s.get("averageHR")
    max_hr = s.get("maxHR")
    calories = s.get("calories", 0)

    lines = [f"{date_str} — {name}"]
    lines.append(f"  Duración: {duration_min} min")

    if avg_hr is not None:
        hr_text = f"  FC: avg {int(avg_hr)}"
        if max_hr is not None:
            hr_text += f" | max {int(max_hr)}"
        lines.append(hr_text)

    exercise_sets = activity.get("exercise_sets", {})
    sets = exercise_sets.get("exerciseSets", [])
    if sets:
        exercises: dict[str, list] = {}
        for s_item in sets:
            if s_item.get("setType") != "ACTIVE":
                continue
            ex_name = s_item.get("exerciseName") or "Ejercicio"
            if ex_name == "UNKNOWN":
                ex_list = s_item.get("exercises", [])
                if ex_list and isinstance(ex_list, list):
                    for ex in ex_list:
                        if isinstance(ex, dict) and ex.get("exerciseName"):
                            ex_name = ex["exerciseName"]
                            break
            exercises.setdefault(ex_name, []).append(s_item)

        for ex_name, ex_sets in exercises.items():
            set_descs = []
            for st in ex_sets:
                reps = st.get("repetitionCount")
                weight = st.get("weight")
                if reps and weight:
                    set_descs.append(f"{reps}x{weight}kg")
                elif reps:
                    set_descs.append(f"{reps} reps")
            lines.append(f"  {ex_name}: {', '.join(set_descs)}")

    if calories:
        lines.append(f"  Calorías: {int(calories)}")

    return "\n".join(lines)


def summarize_activity(activity: dict) -> str:
    type_key = activity.get("summary", {}).get("activityType", {}).get("typeKey", "")
    if type_key in RUNNING_TYPES:
        return summarize_running(activity)
    if type_key in STRENGTH_TYPES:
        return summarize_strength(activity)
    s = activity.get("summary", {})
    name = s.get("activityName", "Actividad")
    date_str = (s.get("startTimeLocal") or "")[:10]
    duration_min = round((s.get("duration", 0) or 0) / 60, 1)
    return f"{date_str} — {name} | {duration_min} min"


def summarize_daily_stats(stats: dict, date_str: str) -> str:
    lines = [f"📅 {date_str}"]

    st = stats.get("stats", {})
    rhr = st.get("restingHeartRate")
    if rhr:
        lines.append(f"  FC reposo: {rhr} bpm")
    steps = st.get("totalSteps")
    if steps:
        lines.append(f"  Pasos: {steps:,}")
    stress = st.get("averageStressLevel")
    if stress:
        lines.append(f"  Estrés promedio: {stress}")
    bb_high = st.get("bodyBatteryHighestValue")
    bb_low = st.get("bodyBatteryLowestValue")
    if bb_high is not None and bb_low is not None:
        lines.append(f"  Body Battery: {bb_low} → {bb_high}")

    sleep = stats.get("sleep", {})
    daily_sleep = sleep.get("dailySleepDTO", {})
    if daily_sleep:
        sleep_secs = daily_sleep.get("sleepTimeSeconds")
        if sleep_secs:
            hours = sleep_secs // 3600
            mins = (sleep_secs % 3600) // 60
            lines.append(f"  Sueño: {hours}h {mins}m")
        scores = daily_sleep.get("sleepScores", {})
        overall = scores.get("overall", {})
        if overall.get("value"):
            lines.append(f"  Sleep Score: {overall['value']} ({overall.get('qualifierKey', '')})")
        deep = scores.get("deepPercentage", {})
        rem = scores.get("remPercentage", {})
        light = scores.get("lightPercentage", {})
        parts = []
        if deep.get("value"):
            parts.append(f"profundo {deep['value']}%")
        if rem.get("value"):
            parts.append(f"REM {rem['value']}%")
        if light.get("value"):
            parts.append(f"ligero {light['value']}%")
        if parts:
            lines.append(f"  Fases: {', '.join(parts)}")

    tr_list = stats.get("training_readiness", [])
    if tr_list and isinstance(tr_list, list) and tr_list:
        tr = tr_list[0] if isinstance(tr_list[0], dict) else {}
        score = tr.get("score")
        if score:
            level = tr.get("level", "")
            lines.append(f"  Training Readiness: {score} ({level})")
            sleep_factor = tr.get("sleepScoreFactorPercent")
            recovery_factor = tr.get("recoveryTimeFactorPercent")
            factors = []
            if sleep_factor is not None:
                factors.append(f"sueño {sleep_factor}%")
            if recovery_factor is not None:
                factors.append(f"recuperación {recovery_factor}%")
            if factors:
                lines.append(f"    Factores: {', '.join(factors)}")

    hrv = stats.get("hrv", {})
    hrv_summary = hrv.get("hrvSummary", {})
    if hrv_summary:
        last_night = hrv_summary.get("lastNightAvg")
        weekly = hrv_summary.get("weeklyAvg")
        status = hrv_summary.get("status", "")
        if last_night or weekly:
            hrv_text = "  HRV:"
            if last_night:
                hrv_text += f" anoche {last_night}"
            if weekly:
                hrv_text += f" | semanal {weekly}"
            if status:
                hrv_text += f" ({status})"
            lines.append(hrv_text)

    return "\n".join(lines)


def build_context_snapshot(activities_dir: Path, stats_dir: Path, days: int = 30) -> str:
    today = date.today()
    cutoff = today - timedelta(days=days)

    activities = load_activities(activities_dir)
    recent = [a for a in activities
              if (a.get("summary", {}).get("startTimeLocal") or "")[:10] >= cutoff.isoformat()]

    all_stats = load_daily_stats(stats_dir)
    recent_stats = [s for s in all_stats if s.get("_date", "") >= cutoff.isoformat()]

    sections = []

    sections.append("## ACTIVIDADES RECIENTES")
    if recent:
        running_count = sum(1 for a in recent
                           if a.get("summary", {}).get("activityType", {}).get("typeKey", "") in RUNNING_TYPES)
        strength_count = sum(1 for a in recent
                            if a.get("summary", {}).get("activityType", {}).get("typeKey", "") in STRENGTH_TYPES)
        sections.append(f"Total: {len(recent)} actividades ({running_count} carrera, {strength_count} fuerza)\n")
        for a in recent:
            sections.append(summarize_activity(a))
            sections.append("")
    else:
        sections.append("Sin actividades en este período.\n")

    sections.append("## ESTADÍSTICAS DIARIAS (últimos 7 días)")
    last_7 = recent_stats[-7:] if len(recent_stats) >= 7 else recent_stats
    for s in last_7:
        sections.append(summarize_daily_stats(s, s.get("_date", "?")))
        sections.append("")

    sections.append("## TENDENCIAS")
    if len(recent_stats) >= 7:
        last_7_stats = recent_stats[-7:]
        prev_7_stats = recent_stats[-14:-7] if len(recent_stats) >= 14 else []

        def avg_metric(stats_list, *keys):
            vals = []
            for s in stats_list:
                obj = s
                for k in keys:
                    if isinstance(obj, dict):
                        obj = obj.get(k)
                    elif isinstance(obj, list) and obj:
                        obj = obj[0].get(k) if isinstance(obj[0], dict) else None
                    else:
                        obj = None
                        break
                if obj is not None and isinstance(obj, (int, float)) and obj > 0:
                    vals.append(obj)
            return round(sum(vals) / len(vals), 1) if vals else None

        rhr_now = avg_metric(last_7_stats, "stats", "restingHeartRate")
        rhr_prev = avg_metric(prev_7_stats, "stats", "restingHeartRate")
        if rhr_now:
            trend = ""
            if rhr_prev:
                diff = rhr_now - rhr_prev
                trend = f" ({'↑' if diff > 0 else '↓'} {abs(diff):.0f} vs semana anterior)" if diff != 0 else " (=)"
            sections.append(f"FC reposo promedio: {rhr_now} bpm{trend}")

        hrv_now = avg_metric(last_7_stats, "hrv", "hrvSummary", "lastNightAvg")
        hrv_prev = avg_metric(prev_7_stats, "hrv", "hrvSummary", "lastNightAvg")
        if hrv_now:
            trend = ""
            if hrv_prev:
                diff = hrv_now - hrv_prev
                trend = f" ({'↑' if diff > 0 else '↓'} {abs(diff):.0f} vs semana anterior)" if diff != 0 else " (=)"
            sections.append(f"HRV promedio: {hrv_now}{trend}")

        tr_now = avg_metric(last_7_stats, "training_readiness", "score")
        tr_prev = avg_metric(prev_7_stats, "training_readiness", "score")
        if tr_now:
            trend = ""
            if tr_prev:
                diff = tr_now - tr_prev
                trend = f" ({'↑' if diff > 0 else '↓'} {abs(diff):.1f} vs semana anterior)" if diff != 0 else " (=)"
            sections.append(f"Training Readiness promedio: {tr_now}{trend}")

        running_acts = [a for a in recent
                        if a.get("summary", {}).get("activityType", {}).get("typeKey", "") in RUNNING_TYPES]
        if running_acts:
            paces = []
            for a in running_acts:
                dist = (a.get("summary", {}).get("distance") or 0) / 1000
                dur = (a.get("summary", {}).get("duration") or 0) / 60
                if dist > 0:
                    paces.append(dur / dist)
            if paces:
                avg_pace = sum(paces) / len(paces)
                p_min = int(avg_pace)
                p_sec = int((avg_pace % 1) * 60)
                sections.append(f"Ritmo promedio running: {p_min}:{p_sec:02d} min/km")

        sections.append(f"Frecuencia: {len(recent)} sesiones en {days} días ({round(len(recent) / (days / 7), 1)}/semana)")

    return "\n".join(sections)
