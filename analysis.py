"""Reads Garmin JSON data and produces human-readable Spanish summaries."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path



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


def summarize_activity(activity: dict) -> str:
    s = activity.get("summary", {})
    name = s.get("activityName", "Actividad")
    type_key = s.get("activityType", {}).get("typeKey", "")
    date_str = (s.get("startTimeLocal") or "")[:10]
    duration_s = s.get("duration", 0) or 0
    duration_min = round(duration_s / 60, 1)

    lines = [f"{date_str} — {name} [{type_key}]"]

    distance_m = s.get("distance")
    if distance_m:
        distance_km = round(distance_m / 1000, 1)
        lines.append(f"  Distancia: {distance_km} km | Duración: {duration_min} min")
        if distance_km > 0 and duration_min > 0:
            pace = duration_min / distance_km
            pace_min = int(pace)
            pace_sec = int((pace % 1) * 60)
            lines.append(f"  Ritmo: {pace_min}:{pace_sec:02d} min/km")
    else:
        lines.append(f"  Duración: {duration_min} min")

    avg_hr = s.get("averageHR")
    if avg_hr is not None:
        hr_text = f"  FC: avg {int(avg_hr)}"
        max_hr = s.get("maxHR")
        if max_hr is not None:
            hr_text += f" | max {int(max_hr)}"
        lines.append(hr_text)

    calories = s.get("calories")
    if calories:
        lines.append(f"  Calorías: {int(calories)}")

    elev_gain = s.get("elevationGain")
    elev_loss = s.get("elevationLoss")
    if elev_gain or elev_loss:
        parts = []
        if elev_gain:
            parts.append(f"+{int(elev_gain)}m")
        if elev_loss:
            parts.append(f"-{int(elev_loss)}m")
        lines.append(f"  Elevación: {' / '.join(parts)}")

    total_sets = s.get("totalSets")
    total_reps = s.get("totalReps")
    if total_sets:
        set_text = f"  Sets: {total_sets}"
        if total_reps:
            set_text += f" | Reps: {total_reps}"
        lines.append(set_text)

    exercise_sets = activity.get("exercise_sets", {})
    ex_list = exercise_sets.get("exerciseSets", [])
    if ex_list:
        exercises: dict[str, list] = {}
        for s_item in ex_list:
            if s_item.get("setType") != "ACTIVE":
                continue
            ex_name = s_item.get("exerciseName") or "Ejercicio"
            if ex_name == "UNKNOWN":
                candidates = s_item.get("exercises", [])
                if candidates and isinstance(candidates, list):
                    for ex in candidates:
                        if isinstance(ex, dict) and ex.get("category"):
                            ex_name = ex["category"]
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

    cadence = s.get("averageRunningCadenceInStepsPerMinute")
    if cadence:
        lines.append(f"  Cadencia: {int(cadence)} spm")
    stride = s.get("avgStrideLength")
    if stride:
        lines.append(f"  Zancada: {round(stride / 100, 2)}m")
    gct = s.get("avgGroundContactTime")
    if gct:
        lines.append(f"  Contacto suelo: {int(gct)}ms")

    avg_power = s.get("avgPower")
    if avg_power:
        power_text = f"  Potencia: avg {int(avg_power)}W"
        max_power = s.get("maxPower")
        if max_power:
            power_text += f" | max {int(max_power)}W"
        lines.append(power_text)

    vo2 = s.get("vO2MaxValue")
    if vo2:
        lines.append(f"  VO2max: {vo2}")

    te_aero = s.get("aerobicTrainingEffect")
    if te_aero:
        lines.append(f"  Training Effect: {te_aero}")
    load = s.get("activityTrainingLoad")
    if load:
        lines.append(f"  Training Load: {round(load, 1)}")
    te_label = s.get("trainingEffectLabel")
    if te_label:
        lines.append(f"  Efecto: {te_label}")

    bb_diff = s.get("differenceBodyBattery")
    if bb_diff is not None:
        lines.append(f"  BB impacto: {bb_diff}")

    hr_zones = activity.get("hr_zones") or []
    if hr_zones:
        zone_parts = []
        for z in hr_zones:
            zn = z.get("zoneNumber", "?")
            secs = z.get("secsInZone", 0)
            if secs > 0:
                zone_parts.append(f"Z{zn}: {round(secs / 60, 1)}min")
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

    return "\n".join(lines)


def summarize_daily_stats(stats: dict, date_str: str, today: date | None = None) -> str:
    is_today = today is not None and date_str == today.isoformat()
    lines = [f"📅 {date_str}"]

    st = stats.get("stats", {})
    rhr = st.get("restingHeartRate")
    if rhr:
        lines.append(f"  FC reposo: {rhr} bpm")
    if not is_today:
        steps = st.get("totalSteps")
        step_goal = st.get("dailyStepGoal")
        if steps is not None:
            step_text = f"  Pasos: {steps:,}"
            if step_goal:
                step_text += f" de {step_goal:,}"
            lines.append(step_text)

    if not is_today:
        stress = st.get("averageStressLevel")
        if stress:
            lines.append(f"  Estrés promedio: {stress}")

    if is_today:
        bb_current = st.get("bodyBatteryMostRecentValue")
        bb_wake = st.get("bodyBatteryAtWakeTime")
        if bb_wake:
            lines.append(f"  BB al despertar: {bb_wake}")
        if bb_current:
            lines.append(f"  BB actual: {bb_current}")
    else:
        bb_high = st.get("bodyBatteryHighestValue")
        bb_low = st.get("bodyBatteryLowestValue")
        if bb_high is not None and bb_low is not None:
            lines.append(f"  Body Battery: {bb_low} → {bb_high}")

    avg_spo2 = st.get("averageSpo2")
    low_spo2 = st.get("lowestSpo2")
    if avg_spo2:
        spo2_text = f"  SpO2: {avg_spo2:.0f}%"
        if low_spo2:
            spo2_text += f" (mín {low_spo2}%)"
        lines.append(spo2_text)

    moderate_min = st.get("moderateIntensityMinutes")
    vigorous_min = st.get("vigorousIntensityMinutes")
    if moderate_min or vigorous_min:
        parts = []
        if moderate_min:
            parts.append(f"{moderate_min}m moderada")
        if vigorous_min:
            parts.append(f"{vigorous_min}m vigorosa")
        lines.append(f"  Intensidad: {', '.join(parts)}")

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


def is_morning_data_ready(stats: dict) -> bool:
    st = stats.get("stats", {})
    bb_wake = st.get("bodyBatteryAtWakeTime")
    if not bb_wake:
        return False
    sleep = stats.get("sleep", {})
    daily_sleep = sleep.get("dailySleepDTO", {})
    scores = daily_sleep.get("sleepScores", {})
    overall = scores.get("overall", {})
    if not overall.get("value"):
        return False
    return True


def summarize_performance_metrics(perf: dict) -> str:
    if not perf:
        return ""
    lines = []

    max_metrics = perf.get("max_metrics", {})
    generic = max_metrics.get("generic", [])
    if generic and isinstance(generic, list):
        vo2 = generic[0].get("vo2MaxPreciseValue")
        if vo2:
            lines.append(f"  VO2max: {vo2}")

    ts = perf.get("training_status", {})
    status = ts.get("currentTrainingStatus")
    if status:
        lines.append(f"  Estado entrenamiento: {status}")

    races = perf.get("race_predictions", [])
    if races and isinstance(races, list):
        rt = races[0].get("raceTime", {})
        if rt:
            race_parts = []
            for dist_name, secs in rt.items():
                if secs and isinstance(secs, (int, float)):
                    mins = int(secs) // 60
                    sec = int(secs) % 60
                    race_parts.append(f"{dist_name}: {mins}:{sec:02d}")
            if race_parts:
                lines.append(f"  Predicciones: {', '.join(race_parts)}")

    endurance = perf.get("endurance_score", {})
    es = endurance.get("overallScore")
    if es:
        lines.append(f"  Endurance Score: {es}")

    lt = perf.get("lactate_threshold", {})
    lt_hr = lt.get("lactateThreshold")
    if lt_hr:
        lines.append(f"  Umbral láctico FC: {lt_hr} bpm")

    lb = perf.get("load_balance", {})
    loads = lb.get("weeklyTrainingLoads", [])
    if loads and isinstance(loads, list) and loads:
        last_load = loads[-1] if isinstance(loads[-1], dict) else {}
        total = last_load.get("totalTrainingLoad")
        if total:
            lines.append(f"  Carga semanal: {round(total, 1)}")

    if not lines:
        return ""
    return "## MÉTRICAS DE RENDIMIENTO\n" + "\n".join(lines)


def build_context_snapshot(activities_dir: Path, stats_dir: Path, days: int = 30, today: date | None = None) -> str:
    today = today or date.today()
    cutoff = today - timedelta(days=days)

    activities = load_activities(activities_dir)
    recent = [a for a in activities
              if (a.get("summary", {}).get("startTimeLocal") or "")[:10] >= cutoff.isoformat()]

    all_stats = load_daily_stats(stats_dir)
    recent_stats = [s for s in all_stats if s.get("_date", "") >= cutoff.isoformat()]

    sections = []

    sections.append("## ACTIVIDADES RECIENTES")
    if recent:
        type_counts: dict[str, int] = {}
        for a in recent:
            tk = a.get("summary", {}).get("activityType", {}).get("typeKey", "other")
            type_counts[tk] = type_counts.get(tk, 0) + 1
        breakdown = ", ".join(f"{cnt} {tk}" for tk, cnt in type_counts.items())
        sections.append(f"Total: {len(recent)} actividades ({breakdown})\n")
        for a in recent:
            sections.append(summarize_activity(a))
            sections.append("")
    else:
        sections.append("Sin actividades en este período.\n")
        type_counts = {}

    if type_counts:
        sections.append("## PERFIL DEPORTIVO")
        sorted_sports = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        sport_list = ", ".join(f"{cnt} {tk}" for tk, cnt in sorted_sports)
        sections.append(f"Deportes practicados (últimos {days} días): {sport_list}")
        sections.append(f"Deporte principal: {sorted_sports[0][0]}")
        sections.append("")

    sections.append("## ESTADÍSTICAS DIARIAS (últimos 7 días)")
    last_7 = recent_stats[-7:] if len(recent_stats) >= 7 else recent_stats
    for s in last_7:
        sections.append(summarize_daily_stats(s, s.get("_date", "?"), today=today))
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

        distance_acts = [a for a in recent if a.get("summary", {}).get("distance")]
        if distance_acts:
            paces = []
            for a in distance_acts:
                dist = (a.get("summary", {}).get("distance") or 0) / 1000
                dur = (a.get("summary", {}).get("duration") or 0) / 60
                if dist > 0:
                    paces.append(dur / dist)
            if paces:
                avg_pace = sum(paces) / len(paces)
                p_min = int(avg_pace)
                p_sec = int((avg_pace % 1) * 60)
                sections.append(f"Ritmo promedio (distancia): {p_min}:{p_sec:02d} min/km")

        sections.append(f"Frecuencia: {len(recent)} sesiones en {days} días ({round(len(recent) / (days / 7), 1)}/semana)")

    perf_file = stats_dir / "performance.json"
    if perf_file.exists():
        perf_data = json.loads(perf_file.read_text())
        perf_section = summarize_performance_metrics(perf_data)
        if perf_section:
            sections.append("")
            sections.append(perf_section)

    return "\n".join(sections)
