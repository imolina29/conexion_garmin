# Conexión Garmin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a terminal-based personal trainer environment that syncs Garmin Forerunner 970 data and provides coaching through Claude Code conversations.

**Architecture:** Python scripts sync data from Garmin Connect API to local JSON files. An analysis script processes raw data into summaries. CLAUDE.md configures Claude as a personal trainer that reads those summaries on demand.

**Tech Stack:** Python 3.13, garminconnect 0.3.20, pandas, python-dotenv. Virtual environment at `.venv/`.

**Spec:** `docs/superpowers/specs/2026-11-01-conexion-garmin-design.md`

## Global Constraints

- Python 3.13+, all scripts run from project root
- Virtual environment at `.venv/` — all pip installs go there
- Credentials in `.env`, never committed — `.env.example` documents required vars
- `data/raw/` is gitignored cache; `data/summaries/` is committed
- `garminconnect>=0.3.20` — unofficial library, no API stability guarantees
- No MFA — direct email/password login
- All dates in ISO format (YYYY-MM-DD)

## Review Focus

1. **Garmin API rate limiting / throttling:** sync fetches many endpoints per activity — if Garmin throttles, the sync should retry with backoff rather than crash or save partial data
2. **Empty activity data:** a strength session with 0 detected sets or a run with no HR data should produce valid (empty/zero) summaries, not crash the analysis
3. **Token expiration mid-sync:** if the session expires during a long sync (--days 90), re-authenticate and continue rather than losing already-fetched data
4. **First run with no data:** analyze.py must produce valid empty summaries when `data/raw/` has no files yet, so the coach experience works even before first sync
5. **Concurrent sync:** running sync.py twice simultaneously could corrupt `.last_sync` or write partial files — use atomic writes (write to temp, rename)

---

### Task 1: Garmin Connect Sync Pipeline

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `sync.py`
- Create: `data/raw/activities/.gitkeep`
- Create: `data/raw/stats/.gitkeep`
- Create: `data/summaries/.gitkeep`
- Test: manual verification — run `sync.py --days 7` and inspect output

**Interfaces:**
- Consumes: Garmin Connect API via `garminconnect` library, credentials from `.env`
- Produces:
  - `data/raw/activities/{activity_id}.json` — one file per activity containing:
    ```json
    {
      "summary": {},
      "exercise_sets": {},
      "splits": {},
      "hr_zones": {},
      "laps": {}
    }
    ```
  - `data/raw/stats/{YYYY-MM-DD}.json` — one file per day containing:
    ```json
    {
      "stats": {},
      "sleep": {},
      "training_readiness": [],
      "hrv": {}
    }
    ```
  - `data/.last_sync` — ISO timestamp of last successful sync

- [ ] **Step 1: Create project scaffold**

Create these files at the project root:

`requirements.txt`:
```
garminconnect>=0.3.20
pandas>=2.0
python-dotenv>=1.0
```

`.env.example`:
```
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
```

`.gitignore`:
```
.venv/
.env
data/raw/
data/.last_sync
__pycache__/
*.pyc
```

Create directories: `data/raw/activities/`, `data/raw/stats/`, `data/summaries/`.

- [ ] **Step 2: Verify venv and dependencies**

Run:
```bash
source .venv/bin/activate && pip list | grep -E "garmin|pandas|dotenv"
```
Expected: garminconnect 0.3.20, pandas, python-dotenv listed.

- [ ] **Step 3: Implement `sync.py` with CLI and authentication**

Implement `sync.py` with these functions:

- `create_client() -> Garmin` — loads `.env`, creates Garmin client, calls `login()` with tokenstore at `data/.garmin_session` for session reuse. Retries once on auth failure.
- `load_last_sync(data_dir: Path) -> datetime | None` — reads `data/.last_sync`, returns datetime or None if missing.
- `save_last_sync(data_dir: Path) -> None` — writes current UTC time to `data/.last_sync` atomically (write tmp, rename).
- `sync_activities(client: Garmin, start_date: str, end_date: str, data_dir: Path) -> int` — calls `client.get_activities_by_date(start_date, end_date)`, for each activity:
  - Skip if `data/raw/activities/{activityId}.json` already exists
  - Fetch `get_activity_details(id)`, `get_activity_hr_in_timezones(id)`, `get_activity_laps(id)`
  - If activityType is strength-related: also fetch `get_activity_exercise_sets(id)`
  - If activityType is running: also fetch `get_activity_splits(id)`
  - Save merged JSON atomically to `data/raw/activities/{activityId}.json`
  - Returns count of new activities synced
- `sync_daily_stats(client: Garmin, start_date: str, end_date: str, data_dir: Path) -> int` — for each date in range:
  - Skip if `data/raw/stats/{date}.json` already exists (except today — always refresh)
  - Fetch `get_stats(date)`, `get_daily_sleep(date)`, `get_training_readiness(date)`, `get_hrv_data(date)`
  - Wrap each API call in try/except to handle missing data gracefully (some days may lack sleep or HRV)
  - Save merged JSON atomically
  - Returns count of days synced
- `main()` — argparse CLI with:
  - `--days N` (default 30): sync last N days
  - `--new`: sync from last_sync timestamp to now (default if no flag)
  - `--today`: sync today only
  - Prints summary: "Synced X new activities, Y days of stats"

Wrap all API calls with a retry decorator: on `GarminConnectConnectionError` or HTTP 429, wait 2s and retry up to 3 times.

- [ ] **Step 4: Create `.env` with real credentials**

Ask Iván to create `.env` with his Garmin email and password.

- [ ] **Step 5: Verify sync works**

Run:
```bash
source .venv/bin/activate && python3 sync.py --days 7
```
Expected: prints "Synced X new activities, Y days of stats", JSON files appear in `data/raw/activities/` and `data/raw/stats/`.

- [ ] **Step 6: Inspect raw data structure**

Read one activity JSON and one stats JSON to verify the data structure is rich enough. For a strength activity, confirm `exercise_sets` has set/rep data. For a running activity, confirm `splits` has per-km data.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore sync.py data/summaries/.gitkeep
git commit -m "feat: add Garmin Connect sync pipeline"
```

---

### Task 2: Data Analysis Engine

**Files:**
- Create: `analyze.py`
- Create: `tests/test_analyze.py`
- Create: `tests/sample_data/` (sample JSON fixtures)
- Produces: `data/summaries/weekly_summary.json`, `data/summaries/running_progress.json`, `data/summaries/strength_log.json`, `data/profile.json`

**Interfaces:**
- Consumes: `data/raw/activities/*.json`, `data/raw/stats/*.json` (format from Task 1)
- Produces:
  - `data/profile.json` — athlete profile with calculated metrics:
    ```json
    {
      "name": "Iván", "age": 33, "weight_kg": 94, "height_cm": 193,
      "bmi": 25.2, "bmr_kcal": 2050, "tdee_estimated_kcal": 3075,
      "protein_target_g": 170, "carb_target_g": 380, "fat_target_g": 100,
      "goals": {"primary": "muscle_gain", "secondary": "run_5k"},
      "updated": "2026-11-01"
    }
    ```
  - `data/summaries/weekly_summary.json` — current + previous week comparison
  - `data/summaries/running_progress.json` — run history, PRs, pace trends
  - `data/summaries/strength_log.json` — session history, sets/volume trends

- [ ] **Step 1: Write failing tests for profile calculations**

`tests/test_analyze.py`:

```python
def test_compute_bmr():
    result = compute_bmr(weight_kg=94, height_cm=193, age=33)
    assert 2000 <= result <= 2100  # Mifflin-St Jeor for male

def test_compute_tdee():
    bmr = 2050
    result = compute_tdee(bmr, activity_level="active")
    assert 3000 <= result <= 3200  # 1.55x multiplier for active

def test_compute_macros_muscle_gain():
    result = compute_macros(weight_kg=94, tdee=3075, goal="muscle_gain")
    assert result["protein_g"] >= 160  # ~1.8g/kg minimum
    assert result["protein_g"] <= 190  # ~2.0g/kg maximum
    assert abs(result["protein_g"] * 4 + result["carb_g"] * 4 + result["fat_g"] * 9 - (3075 + 300)) < 50  # ~+300 surplus
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python3 -m pytest tests/test_analyze.py -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Write failing tests for weekly summary**

```python
def test_compute_weekly_summary_with_mixed_activities(sample_activities):
    result = compute_weekly_summary(sample_activities, week_start=date(2026, 10, 28))
    assert result["total_sessions"] == 4
    assert result["strength_sessions"] == 2
    assert result["running_sessions"] == 2
    assert result["total_km_run"] > 0
    assert result["avg_hr"] > 0

def test_compute_weekly_summary_empty():
    result = compute_weekly_summary([], week_start=date(2026, 10, 28))
    assert result["total_sessions"] == 0
    assert result["total_km_run"] == 0
```

Create `tests/sample_data/` with fixture JSON files: 2 running activities and 2 strength activities with realistic Garmin data structure matching Task 1's output format. Use a pytest `conftest.py` fixture that loads them.

- [ ] **Step 4: Write failing tests for running progress**

```python
def test_compute_running_progress(sample_activities):
    result = compute_running_progress(sample_activities)
    assert len(result["recent_runs"]) > 0
    assert all("avg_pace_min_per_km" in r for r in result["recent_runs"])
    assert "pace_trend_by_week" in result

def test_compute_running_progress_no_runs():
    result = compute_running_progress([])
    assert result["recent_runs"] == []
    assert result["total_km"] == 0
```

- [ ] **Step 5: Write failing tests for strength log**

```python
def test_compute_strength_log(sample_activities):
    result = compute_strength_log(sample_activities)
    assert result["total_sessions_30d"] >= 0
    assert "avg_sets_per_session" in result
    assert "volume_trend_by_week" in result

def test_compute_strength_log_no_sets():
    # Strength activity where watch detected 0 sets
    result = compute_strength_log([sample_strength_no_sets])
    assert result["total_sessions_30d"] == 1
    assert result["avg_sets_per_session"] == 0
```

- [ ] **Step 6: Run all tests to verify they fail**

Run: `source .venv/bin/activate && python3 -m pytest tests/test_analyze.py -v`
Expected: all FAIL.

- [ ] **Step 7: Implement `analyze.py`**

Functions to implement in `analyze.py`:

- `load_activities(raw_dir: Path) -> list[dict]` — read all `data/raw/activities/*.json`, return sorted by date descending
- `load_daily_stats(raw_dir: Path) -> list[dict]` — read all `data/raw/stats/*.json`
- `compute_bmr(weight_kg: float, height_cm: float, age: int) -> float` — Mifflin-St Jeor formula for male
- `compute_tdee(bmr: float, activity_level: str) -> float` — BMR × activity multiplier (1.55 for "active")
- `compute_macros(weight_kg: float, tdee: float, goal: str) -> dict` — protein at 1.8-2.0g/kg, +300kcal surplus for muscle_gain, rest split 50/30 carb/fat
- `compute_weekly_summary(activities: list[dict], week_start: date) -> dict` — aggregate sessions by type, total duration/calories/km, avg HR. Also compute previous week for comparison.
- `compute_running_progress(activities: list[dict]) -> dict` — filter running activities, extract pace/distance/HR per run, calculate PRs at 1km/3km/4km/5km from splits data, pace trend by week
- `compute_strength_log(activities: list[dict]) -> dict` — filter strength activities, extract sets/reps from exercise_sets, avg duration, frequency by weekday, volume trend by week
- `build_profile() -> dict` — hardcoded athlete data + computed BMR/TDEE/macros
- `main()` — load raw data, compute all summaries, write to `data/summaries/` and `data/profile.json`

Classify activities by checking `summary.activityType.typeKey`: `"running"` or `"treadmill_running"` for running, `"strength_training"` for strength.

- [ ] **Step 8: Run tests to verify they pass**

Run: `source .venv/bin/activate && python3 -m pytest tests/test_analyze.py -v`
Expected: all PASS.

- [ ] **Step 9: Run analyze.py against real synced data**

Run:
```bash
source .venv/bin/activate && python3 analyze.py
```
Expected: summary files created in `data/summaries/`, `data/profile.json` created. Read each file to verify content is reasonable.

- [ ] **Step 10: Commit**

```bash
git add analyze.py tests/ data/profile.json data/summaries/
git commit -m "feat: add data analysis engine with weekly/running/strength summaries"
```

---

### Task 3: Personal Trainer Experience

**Files:**
- Create: `CLAUDE.md`
- Create: `.claude/settings.json`

**Interfaces:**
- Consumes: `data/summaries/*.json`, `data/profile.json` (paths from Task 2)
- Produces: a working personal trainer conversation experience in Claude Code

- [ ] **Step 1: Write CLAUDE.md**

Create `CLAUDE.md` at project root with these sections:

**Role:** "Eres el entrenador personal de Iván. Tienes acceso a sus datos reales de entrenamiento del Garmin Forerunner 970."

**Auto-sync instruction:** "Al inicio de cada conversación, ejecuta: `source .venv/bin/activate && python3 sync.py --new && python3 analyze.py` para sincronizar datos nuevos. Reporta brevemente si hubo actividades nuevas."

**Data access instructions:** "Cuando necesites métricas, usa la herramienta Read para leer estos archivos:
- `data/profile.json` — perfil del atleta, TDEE, macros
- `data/summaries/weekly_summary.json` — resumen semanal
- `data/summaries/running_progress.json` — progreso de carrera
- `data/summaries/strength_log.json` — registro de fuerza
Para datos detallados de una actividad específica: `data/raw/activities/{id}.json`"

**Athlete profile:** Include Iván's fixed data (33yo, 94kg, 193cm) and goals (muscle gain primary, 5k secondary).

**Coaching protocols:**
- Análisis de carrera: revisar ritmo por km, zonas de HR, cadencia. Comparar con sesiones anteriores. Sugerir ajustes de ritmo para alcanzar 5km.
- Análisis de fuerza: revisar volumen (sets × reps), duración de descanso, frecuencia por grupo muscular. Verificar que todos los grupos se trabajen al menos 2x/semana.
- Recuperación: si HR en reposo sube >5bpm, o sueño <6h, o training readiness baja, sugerir descanso.
- Progresión: sugerir incrementos graduales — +5-10% volumen semanal en fuerza, +0.5km o -15s/km en carrera.

**Nutrition guidelines:**
- Meta calórica: TDEE + 300kcal (superávit para ganar masa)
- Proteína: 1.8-2.0g/kg (~170-188g/día)
- Distribución: 5-6 comidas, proteína en cada una
- Pre-entreno (2h antes): carbohidratos complejos + proteína moderada
- Post-entreno (30min-1h): proteína rápida + carbohidratos simples
- Sugerir comidas concretas con alimentos accesibles: pollo, huevos, arroz, avena, atún, carne, legumbres, leche, queso, frutas, verduras

**Communication style:** Hablar en español, tono directo y motivacional, usar datos concretos. Cuando el usuario pregunte algo genérico, leer los resúmenes primero para dar respuestas basadas en datos.

- [ ] **Step 2: Configure auto-sync hook**

Create `.claude/settings.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "if [ ! -f data/.session_synced ]; then source .venv/bin/activate && python3 sync.py --new && python3 analyze.py && touch data/.session_synced; fi",
        "timeout": 30000
      }
    ]
  }
}
```

This runs sync once per session (the `.session_synced` flag prevents re-running on every message). Add `data/.session_synced` to `.gitignore`.

If the `UserPromptSubmit` hook event is not available, fall back to the CLAUDE.md auto-sync instruction as the primary mechanism.

- [ ] **Step 3: Verify the full experience**

1. Open a new Claude Code session in the project directory
2. Send "Hola coach, ¿cómo estuvo mi última sesión?"
3. Verify Claude reads the summaries and gives a data-driven response
4. Ask "¿Qué debería comer mañana?" — verify nutrition advice uses profile macros
5. Ask "¿Cómo va mi progreso en carrera?" — verify it references running_progress.json data

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .claude/settings.json .gitignore
git commit -m "feat: add personal trainer CLAUDE.md and auto-sync hook"
```
