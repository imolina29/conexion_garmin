# Garmin Coach Telegram Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Telegram bot backed by Claude that reads the user's Garmin data and answers questions about their training, metrics, and progress in natural Spanish.

**Architecture:** Three layers — (1) an analysis module that reads raw JSON files and produces structured summaries + trend data, (2) a Telegram bot that receives messages and dispatches them to Claude with Garmin context, (3) auto-sync that keeps data fresh before each response. The analysis module builds a compact text snapshot of the user's data that fits in Claude's context alongside conversation history. The bot runs as a long-polling process.

**Tech Stack:** Python 3.13, python-telegram-bot 21.x, anthropic SDK, existing garminconnect + sync.py.

**Spec:** `docs/superpowers/specs/2026-11-02-garmin-telegram-coach-design.md`

## Global Constraints

- Python 3.13, single-user bot.
- All responses in Spanish.
- No prescriptive training plans — observe, interpret, educate.
- Secrets via `.env`: `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`.
- Existing `sync.py` is the sync engine — import and reuse, don't rewrite.

## File Structure

```
conexion_Garmin/
├── sync.py                    # existing — sync engine (modify: extract client creation)
├── analysis.py                # NEW — reads raw JSON, produces summaries + trends
├── bot.py                     # NEW — Telegram bot + Claude integration
├── requirements.txt           # modify — add python-telegram-bot, anthropic
├── .env.example               # modify — add new keys
├── tests/
│   ├── test_analysis.py       # NEW — unit tests for analysis module
│   └── test_bot.py            # NEW — unit tests for bot context building
└── data/
    └── raw/                   # existing JSON files
```

## Review Focus

1. **Empty data ranges:** User asks about a week with zero activities — analysis must return "no activities" text, not crash on empty lists.
2. **Garmin API down during auto-sync:** Bot must still answer from last-synced data, not fail the entire response.
3. **Activity with missing optional fields:** Some activities lack HR, distance, or exercise sets — summary must degrade gracefully.
4. **Claude API rate limit or timeout:** Bot must reply with a user-friendly error, not hang silently.
5. **Very long conversation history:** Context must be bounded so Claude's token limit isn't exceeded.

---

### Task 1: Analysis Module — Data Loading and Activity Summaries

**Files:**
- Create: `analysis.py`
- Create: `tests/test_analysis.py`

**Interfaces:**
- Consumes: JSON files in `data/raw/activities/` and `data/raw/stats/`
- Produces:
  - `load_activities(activities_dir: Path) -> list[dict]` — returns list of activity summary dicts
  - `load_daily_stats(stats_dir: Path) -> list[dict]` — returns list of daily stat dicts
  - `summarize_activity(activity: dict) -> str` — one-paragraph Spanish text for a single activity
  - `summarize_running(activity: dict) -> str` — running-specific summary with pace, splits, HR zones
  - `summarize_strength(activity: dict) -> str` — strength-specific summary with exercises, sets, reps
  - `summarize_daily_stats(stats: dict, date_str: str) -> str` — one-paragraph Spanish text for a day's stats
  - `build_context_snapshot(activities_dir: Path, stats_dir: Path, days: int = 30) -> str` — full text snapshot for LLM context

- [ ] **Step 1: Write failing test for `load_activities`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL — `cannot import name 'load_activities'`

- [ ] **Step 3: Implement `load_activities` and `load_daily_stats` in `analysis.py`**

`load_activities` reads all `.json` files from the directory, parses them, sorts by `summary.startTimeLocal` ascending. `load_daily_stats` reads all `.json` from stats dir, sorts by filename (date string). Both return empty list for empty/missing directories.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analysis.py -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for `summarize_activity`, `summarize_running`, `summarize_strength`**

```python
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
    assert isinstance(result, str)  # no crash
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL

- [ ] **Step 7: Implement `summarize_activity`, `summarize_running`, `summarize_strength`**

`summarize_activity` dispatches to `summarize_running` or `summarize_strength` based on `activityType.typeKey`. Running summaries include: date, name, distance (km), duration (min), pace (min/km), avg/max HR, HR zone distribution, split paces. Strength summaries include: date, name, duration, exercises grouped with sets/reps/weight. All text in Spanish. Handle `None` values for optional fields gracefully — omit the line rather than crash.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_analysis.py -v`
Expected: PASS

- [ ] **Step 9: Write failing tests for `summarize_daily_stats`**

```python
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
    assert "48" in result  # resting HR
    assert "72" in result  # sleep score
    assert "65" in result  # TR score

def test_summarize_daily_stats_missing_sleep():
    stats = {"stats": {"restingHeartRate": 50, "totalSteps": 3000},
             "sleep": {}, "training_readiness": [], "hrv": {}}
    result = summarize_daily_stats(stats, "2026-10-15")
    assert "50" in result
    assert isinstance(result, str)
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `pytest tests/test_analysis.py -v`
Expected: FAIL

- [ ] **Step 11: Implement `summarize_daily_stats`**

Produces a paragraph per day including: resting HR (and what the value means), sleep score + breakdown (deep/REM/light percentages with qualifier), Training Readiness score + level + contributing factors, HRV last night + weekly average + status. Omit sections where data is empty. All in Spanish.

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_analysis.py -v`
Expected: PASS

- [ ] **Step 13: Write failing test for `build_context_snapshot`**

```python
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
```

- [ ] **Step 14: Implement `build_context_snapshot`**

Loads activities from last N days, loads daily stats from last N days. Produces a structured text document with sections: "ACTIVIDADES RECIENTES" (each activity summarized), "ESTADÍSTICAS DIARIAS" (last 7 days detailed, rest weekly averages), "TENDENCIAS" (compare last 7 days vs previous 7 days for key metrics: avg pace, avg resting HR, avg sleep score, avg HRV, activity frequency). Cap output to ~3000 words to leave room for conversation in Claude's context.

- [ ] **Step 15: Run all tests**

Run: `pytest tests/test_analysis.py -v`
Expected: ALL PASS

- [ ] **Step 16: Commit**

```bash
git add analysis.py tests/test_analysis.py
git commit -m "feat: add analysis module with activity and stats summaries"
```

---

### Task 2: Telegram Bot with Claude Integration

**Files:**
- Create: `bot.py`
- Create: `tests/test_bot.py`
- Modify: `requirements.txt` — add `python-telegram-bot>=21.0`, `anthropic>=0.40`
- Modify: `.env.example` — add `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`

**Interfaces:**
- Consumes:
  - `analysis.build_context_snapshot(activities_dir: Path, stats_dir: Path, days: int) -> str`
  - `sync.create_client() -> Garmin` and `sync.sync_activities(client, start, end)`, `sync.sync_daily_stats(client, start, end)`
- Produces:
  - `build_system_prompt(garmin_snapshot: str) -> str` — assembles Claude system prompt with metric explanations + user data
  - `handle_message(update, context)` — Telegram handler that syncs, builds context, calls Claude, replies
  - `main()` — starts the bot with long polling

- [ ] **Step 1: Add dependencies to `requirements.txt`**

Append `python-telegram-bot>=21.0` and `anthropic>=0.40`.

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`

- [ ] **Step 3: Update `.env.example`**

Add `TELEGRAM_BOT_TOKEN=` and `ANTHROPIC_API_KEY=`.

- [ ] **Step 4: Write failing test for `build_system_prompt`**

```python
def test_build_system_prompt_includes_snapshot():
    snapshot = "ACTIVIDADES: Carrera 5km en 30min"
    result = build_system_prompt(snapshot)
    assert "Carrera 5km" in result
    assert "coach" in result.lower() or "entrenador" in result.lower()

def test_build_system_prompt_includes_metric_explanations():
    result = build_system_prompt("datos vacíos")
    assert "HRV" in result
    assert "Training Readiness" in result
    assert "FC en reposo" in result or "frecuencia cardíaca" in result.lower()
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `pytest tests/test_bot.py -v`
Expected: FAIL

- [ ] **Step 6: Implement `build_system_prompt`**

The system prompt has three parts: (1) role — "Eres un coach de entrenamiento personal que analiza datos de Garmin", with personality: claro, directo, educativo, en español; (2) metric reference — a concise explanation of each Garmin metric (HRV: variabilidad del ritmo cardíaco, refleja recuperación del sistema nervioso autónomo, valores más altos = mejor recuperado; Training Readiness: score 0-100 basado en sueño, recuperación y carga de entrenamiento; Sleep Score: 0-100 con breakdown de profundo/REM/ligero; FC en reposo: indicador de fitness cardiovascular, más bajo = mejor condición; Body Battery: energía estimada 0-100; zonas de FC: zona 1-5 de fácil a máximo esfuerzo); (3) the user's data snapshot.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: PASS

- [ ] **Step 8: Write failing test for conversation history management**

```python
def test_conversation_history_bounded():
    history = ConversationHistory(max_messages=10)
    for i in range(15):
        history.add("user", f"message {i}")
        history.add("assistant", f"response {i}")
    messages = history.get_messages()
    assert len(messages) == 10  # bounded
    assert messages[0]["content"] == "message 10"  # oldest kept

def test_conversation_history_to_claude_format():
    history = ConversationHistory(max_messages=10)
    history.add("user", "hola")
    history.add("assistant", "hola, ¿cómo te fue?")
    messages = history.get_messages()
    assert messages[0] == {"role": "user", "content": "hola"}
    assert messages[1] == {"role": "assistant", "content": "hola, ¿cómo te fue?"}
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `pytest tests/test_bot.py -v`
Expected: FAIL

- [ ] **Step 10: Implement `ConversationHistory` class**

Simple list-based store with a max size. `add(role, content)` appends, trims from the front if over limit. `get_messages()` returns list of `{"role": ..., "content": ...}` dicts. `clear()` resets. Single-user, in-memory is sufficient.

- [ ] **Step 11: Run tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: PASS

- [ ] **Step 12: Implement `handle_message` and `main` in `bot.py`**

`handle_message` flow: (1) run sync for today (import sync functions, catch errors — if sync fails, log and continue with stale data), (2) build context snapshot via `build_context_snapshot`, (3) build system prompt, (4) get conversation history, (5) call Claude API with system prompt + history + new user message, (6) add both messages to history, (7) send Claude's response back via Telegram. `main()` loads env, creates `Application` from python-telegram-bot, registers the message handler, starts long-polling. Handle Claude API errors by replying "Hubo un error procesando tu mensaje, intenta de nuevo."

- [ ] **Step 13: Manual integration test**

Run: `python bot.py` — verify bot starts, send a test message from Telegram, verify it responds with Garmin data context.

- [ ] **Step 14: Commit**

```bash
git add bot.py tests/test_bot.py requirements.txt .env.example
git commit -m "feat: add Telegram bot with Claude integration"
```

---

### Task 3: Sync Integration and Auto-Sync

**Files:**
- Modify: `sync.py` — refactor `create_client` and sync functions to be importable without running `main()`
- Modify: `bot.py` — add pre-response sync logic with error handling

**Interfaces:**
- Consumes: `sync.create_client`, `sync.sync_activities`, `sync.sync_daily_stats`, `sync.save_last_sync`
- Produces: `run_sync_safe() -> bool` in `bot.py` — runs sync, returns True on success, False on failure

- [ ] **Step 1: Verify `sync.py` is cleanly importable**

Run: `python -c "from sync import create_client, sync_activities, sync_daily_stats, save_last_sync"` — should succeed without side effects since `main()` is guarded by `if __name__`.

- [ ] **Step 2: Write failing test for `run_sync_safe`**

```python
def test_run_sync_safe_returns_false_on_error(monkeypatch):
    monkeypatch.setattr("bot.create_client", lambda: (_ for _ in ()).throw(Exception("auth failed")))
    result = run_sync_safe()
    assert result is False

def test_run_sync_safe_returns_true_on_success(monkeypatch):
    monkeypatch.setattr("bot.create_client", lambda: MockClient())
    monkeypatch.setattr("bot.sync_activities", lambda *a: 0)
    monkeypatch.setattr("bot.sync_daily_stats", lambda *a: 0)
    monkeypatch.setattr("bot.save_last_sync", lambda: None)
    result = run_sync_safe()
    assert result is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_bot.py::test_run_sync_safe_returns_false_on_error -v`
Expected: FAIL

- [ ] **Step 4: Implement `run_sync_safe` in `bot.py`**

Imports sync functions. Creates client, syncs last 2 days of activities and stats (keeps it fast), calls `save_last_sync`. Wraps everything in try/except — returns `True` on success, `False` on any exception (logs the error).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: ALL PASS

- [ ] **Step 6: Wire `run_sync_safe` into `handle_message`**

At the start of `handle_message`, call `run_sync_safe()`. If it returns `False`, prepend a note to the bot's context: "Nota: no se pudieron actualizar los datos, usando última sincronización disponible."

- [ ] **Step 7: Manual end-to-end test**

Run `python bot.py`, send message from Telegram, verify: (1) sync runs before response, (2) response includes recent data, (3) if Garmin is unreachable, bot still responds with stale data.

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add sync.py bot.py tests/test_bot.py
git commit -m "feat: add auto-sync before bot responses"
```
