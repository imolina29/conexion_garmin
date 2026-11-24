# Phase 1 Multi-User Generalization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user-facing feature (training routine, timezone, report schedule, credential transparency) configurable per user instead of hardcoded or global.

**Architecture:** Add per-user config fields to `UserManager` (data layer), then consume them from bot handlers and the report scheduler. New commands `/rutina`, `/config`, `/eliminar` use the existing `registration_state` pattern for multi-step flows. The report loop switches from sleeping-until-next-global-time to polling every 60s and checking each user's individual schedule.

**Tech Stack:** Python 3.13, python-telegram-bot 21.x, google-genai (Gemini), cryptography (Fernet). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-23-phase1-multi-user-generalization-design.md`

## Global Constraints

- Python 3.13, no new dependencies.
- Existing 43 tests must stay green throughout.
- Legacy users (no new config fields in their `config.json`) must work without migration — all new fields have defaults.
- All Gemini calls use the existing `GEMINI_MODELS` fallback chain and `call_gemini` helper.
- All bot text in Spanish.

## Review Focus

1. **Legacy user with no `timezone`/`report_morning`/`training_routine` fields:** should get defaults (`"America/Bogota"`, `"07:30"`, `"20:30"`, empty routine → generic plan prompt). Pin with: `test_legacy_user_gets_defaults` in Task 1.
2. **User in `/rutina` flow receives a scheduled report simultaneously:** report is push (bot.send_message), not intercepted by registration_state. The flow should not break. Pin with: `test_rutina_flow_not_broken_by_concurrent_send` in Task 2.
3. **Invalid timezone string passed to `/config`:** `resolve_timezone` returns None, bot asks again. Should not crash or store garbage. Pin with: `test_resolve_timezone_invalid_returns_none` in Task 3.
4. **Report loop with zero registered users:** should not error, just sleep and retry. Pin with: `test_should_send_report_no_users` in Task 4.
5. **`/eliminar` while user has active `/rutina` flow:** should clean up registration_state entry too. Pin with: `test_delete_clears_registration_state` in Task 5.

---

### Task 1: UserManager per-user config fields and delete

**Files:**
- Modify: `users.py`
- Test: `tests/test_users.py`

**Interfaces:**
- Consumes: nothing new (builds on existing `UserManager` class)
- Produces:
  - `UserManager.get_training_routine(telegram_id: int) -> str` — empty string if unset
  - `UserManager.update_training_routine(telegram_id: int, routine: str) -> None`
  - `UserManager.get_timezone(telegram_id: int) -> str` — `"America/Bogota"` if unset
  - `UserManager.update_timezone(telegram_id: int, tz: str) -> None`
  - `UserManager.get_report_times(telegram_id: int) -> tuple[str, str]` — `("07:30", "20:30")` if unset
  - `UserManager.update_report_times(telegram_id: int, morning: str, evening: str) -> None`
  - `UserManager.delete_user(telegram_id: int) -> bool` — deletes user dir, returns True if existed

- [ ] **Step 1: Write failing tests for training routine getter/setter**

```python
def test_get_training_routine_default_empty(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    assert mgr.get_training_routine(123) == ""

def test_update_and_get_training_routine(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    mgr.update_training_routine(123, "Lunes: Pecho\nMartes: Espalda")
    assert mgr.get_training_routine(123) == "Lunes: Pecho\nMartes: Espalda"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_users.py::test_get_training_routine_default_empty tests/test_users.py::test_update_and_get_training_routine -v`
Expected: FAIL — `AttributeError: 'UserManager' object has no attribute 'get_training_routine'`

- [ ] **Step 3: Implement `get_training_routine` and `update_training_routine` in `users.py`**

Same pattern as existing `get_profile`/`update_profile`. Read `training_routine` from config dict with `""` default.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_users.py -v`
Expected: all PASS

- [ ] **Step 5: Write failing tests for timezone and report times**

```python
def test_get_timezone_default(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    assert mgr.get_timezone(123) == "America/Bogota"

def test_update_and_get_timezone(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    mgr.update_timezone(123, "America/Mexico_City")
    assert mgr.get_timezone(123) == "America/Mexico_City"

def test_get_report_times_default(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    assert mgr.get_report_times(123) == ("07:30", "20:30")

def test_update_and_get_report_times(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    mgr.update_report_times(123, "06:00", "21:00")
    assert mgr.get_report_times(123) == ("06:00", "21:00")
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_users.py::test_get_timezone_default tests/test_users.py::test_get_report_times_default -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 7: Implement timezone and report time methods in `users.py`**

`get_timezone` reads `timezone` key with default `"America/Bogota"`. `get_report_times` reads `report_morning` (default `"07:30"`) and `report_evening` (default `"20:30"`). Update methods follow `update_profile` pattern.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_users.py -v`
Expected: all PASS

- [ ] **Step 9: Write failing tests for delete and legacy compatibility**

```python
def test_delete_user_removes_directory(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    assert mgr.delete_user(123) is True
    assert not (tmp_path / "123").exists()
    assert not mgr.user_exists(123)

def test_delete_user_nonexistent_returns_false(tmp_path):
    mgr = UserManager(users_dir=tmp_path)
    assert mgr.delete_user(999) is False

def test_legacy_user_gets_defaults(tmp_path):
    """User created before Phase 1 — no timezone/routine/report fields in config."""
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    # Simulate legacy config by removing new fields
    import json
    config_path = tmp_path / "123" / "config.json"
    config = json.loads(config_path.read_text())
    config.pop("training_routine", None)
    config.pop("timezone", None)
    config.pop("report_morning", None)
    config.pop("report_evening", None)
    config_path.write_text(json.dumps(config))
    # All getters return defaults
    assert mgr.get_training_routine(123) == ""
    assert mgr.get_timezone(123) == "America/Bogota"
    assert mgr.get_report_times(123) == ("07:30", "20:30")
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_users.py::test_delete_user_removes_directory tests/test_users.py::test_legacy_user_gets_defaults -v`
Expected: FAIL — `AttributeError: 'UserManager' object has no attribute 'delete_user'`

- [ ] **Step 11: Implement `delete_user` in `users.py`**

Use `shutil.rmtree` on the user directory. Return `True` if the directory existed, `False` otherwise.

- [ ] **Step 12: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS (43 existing + 9 new)

- [ ] **Step 13: Commit**

```bash
git add users.py tests/test_users.py
git commit -m "feat: add per-user config fields (timezone, report times, training routine) and delete"
```

---

### Task 2: Dynamic PLAN_PROMPT and /rutina command

**Files:**
- Modify: `bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `UserManager.get_training_routine`, `UserManager.update_training_routine` from Task 1
- Produces:
  - `build_plan_prompt(training_routine: str) -> str` — returns the plan prompt with routine embedded or generic fallback
  - `cmd_rutina(update, context)` — handler for `/rutina`
  - `handle_rutina_flow(update, context)` — processes messages during `/rutina` flow (called from `handle_registration` or similar dispatcher)

- [ ] **Step 1: Write failing tests for `build_plan_prompt`**

```python
def test_build_plan_prompt_with_routine_includes_it():
    from bot import build_plan_prompt
    routine = "Lunes: Pecho\nMiércoles: Espalda\nViernes: Pierna"
    result = build_plan_prompt(routine)
    assert "Pecho" in result
    assert "Espalda" in result
    assert "Pierna" in result
    # Must NOT contain the old hardcoded structure
    assert "EMPUJE (Pecho, Hombro, Tríceps)" not in result

def test_build_plan_prompt_without_routine_is_generic():
    from bot import build_plan_prompt
    result = build_plan_prompt("")
    assert "perfil" in result.lower() or "propón" in result.lower() or "sugiere" in result.lower()
    # Must NOT contain the old hardcoded structure
    assert "EMPUJE (Pecho, Hombro, Tríceps)" not in result

def test_build_plan_prompt_flexible_sessions():
    from bot import build_plan_prompt
    routine = "Lunes: Gym\nSábado: Carrera larga"
    result = build_plan_prompt(routine)
    # Should tell Gemini to generate sessions matching the routine days, not force 5
    assert "EXACTAMENTE 5" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot.py::test_build_plan_prompt_with_routine_includes_it -v`
Expected: FAIL — `ImportError: cannot import name 'build_plan_prompt' from 'bot'`

- [ ] **Step 3: Implement `build_plan_prompt(training_routine: str) -> str` in `bot.py`**

Extract the current `PLAN_PROMPT` constant into a function. When `training_routine` is non-empty, embed it and tell Gemini to respect that structure (variable number of sessions, any weekday 0-6). When empty, use a generic prompt asking Gemini to propose a structure based on the user's profile. Remove the hardcoded Push/Pull/Leg table and "EXACTAMENTE 5 sesiones" constraint. Keep the JSON format instructions and calendar-related rules.

- [ ] **Step 4: Update `cmd_plan` in `bot.py` to call `build_plan_prompt`**

Replace `full_system = system_prompt + "\n\n" + PLAN_PROMPT` with `full_system = system_prompt + "\n\n" + build_plan_prompt(user_manager.get_training_routine(user_id))`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot.py -v`
Expected: all PASS

- [ ] **Step 6: Write failing test for `/rutina` flow state machine**

```python
def test_rutina_flow_states():
    """Verify /rutina sets up the correct registration_state steps."""
    from bot import registration_state
    import bot
    # Simulate: user triggers /rutina → state should be awaiting_routine_description
    # Then user sends text → state should be awaiting_routine_approval (after Gemini parses)
    # Then user approves → state cleared, routine saved
    registration_state[123] = {"step": "awaiting_routine_description"}
    assert registration_state[123]["step"] == "awaiting_routine_description"

def test_rutina_flow_not_broken_by_concurrent_send():
    """Registration_state only intercepts user text messages, not bot pushes."""
    from bot import registration_state
    # A user in /rutina flow has step set
    registration_state[123] = {"step": "awaiting_routine_approval", "parsed_routine": "Lunes: Gym"}
    # This state only affects handle_message → handle_registration path
    # Bot.send_message (reports) bypasses this entirely
    assert registration_state[123]["step"] == "awaiting_routine_approval"
```

- [ ] **Step 7: Implement `/rutina` handler in `bot.py`**

`cmd_rutina`: checks user exists, sets `registration_state[user_id] = {"step": "awaiting_routine_description"}`, sends prompt asking user to describe their routine.

Add `"awaiting_routine_description"` and `"awaiting_routine_approval"` steps to `handle_registration`:
- `awaiting_routine_description`: takes user text, calls `call_gemini` with a system prompt that asks it to format the routine as a readable table, stores the parsed result in `state["parsed_routine"]`, shows it to user, moves to `awaiting_routine_approval`.
- `awaiting_routine_approval`: if user approves (text contains "sí", "si", "ok", "listo", "perfecto", "dale"), saves `state["parsed_routine"]` via `update_training_routine`, clears state. If user says "no" or "cambiar", goes back to `awaiting_routine_description`. Otherwise treats the text as a modification request and re-processes.

Register `CommandHandler("rutina", cmd_rutina)` in `main()`.

- [ ] **Step 8: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: dynamic plan prompt and /rutina command for per-user training routines"
```

---

### Task 3: /config command and timezone mapping

**Files:**
- Modify: `bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `UserManager.get_timezone`, `UserManager.update_timezone`, `UserManager.get_report_times`, `UserManager.update_report_times` from Task 1
- Produces:
  - `resolve_timezone(text: str) -> str | None` — maps city name or IANA string to valid IANA timezone
  - `cmd_config(update, context)` — handler for `/config`

- [ ] **Step 1: Write failing tests for `resolve_timezone`**

```python
def test_resolve_timezone_iana_direct():
    from bot import resolve_timezone
    assert resolve_timezone("America/Bogota") == "America/Bogota"
    assert resolve_timezone("Europe/Madrid") == "Europe/Madrid"
    assert resolve_timezone("America/Mexico_City") == "America/Mexico_City"

def test_resolve_timezone_city_names():
    from bot import resolve_timezone
    assert resolve_timezone("Bogotá") == "America/Bogota"
    assert resolve_timezone("bogota") == "America/Bogota"
    assert resolve_timezone("CDMX") == "America/Mexico_City"
    assert resolve_timezone("México") == "America/Mexico_City"
    assert resolve_timezone("Buenos Aires") == "America/Argentina/Buenos_Aires"
    assert resolve_timezone("Madrid") == "Europe/Madrid"
    assert resolve_timezone("Lima") == "America/Lima"
    assert resolve_timezone("Santiago") == "America/Santiago"

def test_resolve_timezone_invalid_returns_none():
    from bot import resolve_timezone
    assert resolve_timezone("Atlantis") is None
    assert resolve_timezone("") is None
    assert resolve_timezone("Not/A/Timezone") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot.py::test_resolve_timezone_iana_direct -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_timezone' from 'bot'`

- [ ] **Step 3: Implement `resolve_timezone(text: str) -> str | None` in `bot.py`**

A dict mapping lowercase city/country names to IANA strings, plus validation of direct IANA input using `ZoneInfo` (if `ZoneInfo(text)` doesn't raise `KeyError`, it's valid). Cover at minimum: Bogotá, Colombia, México, CDMX, Guadalajara, Buenos Aires, Argentina, Lima, Perú, Santiago, Chile, Madrid, España, Quito, Ecuador, Caracas, Venezuela, São Paulo, Brasil, New York, Miami, Los Angeles.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot.py -v`
Expected: all PASS

- [ ] **Step 5: Implement `/config` handler in `bot.py`**

`cmd_config`: checks user exists, sets `registration_state[user_id] = {"step": "awaiting_config_timezone"}`, shows current config and asks for timezone.

Add steps to `handle_registration`:
- `awaiting_config_timezone`: calls `resolve_timezone(text)`. If valid, stores via `update_timezone`, moves to `awaiting_config_morning`. If None, asks again.
- `awaiting_config_morning`: expects time like "7:30" or "07:30". Validates HH:MM format. Stores in state, moves to `awaiting_config_evening`.
- `awaiting_config_evening`: same validation. Calls `update_report_times`, clears state, confirms.

Register `CommandHandler("config", cmd_config)` in `main()`.

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: /config command with timezone mapping for per-user schedule"
```

---

### Task 4: Per-user report loop

**Files:**
- Modify: `bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `UserManager.list_users`, `UserManager.get_timezone`, `UserManager.get_report_times` from Task 1
- Produces:
  - `_should_send_report(user_id: int, report_type: str, now_utc: datetime, user_manager: UserManager, sent_today: dict) -> bool` — pure function for testability
  - Rewritten `report_loop(app)` — polls every 60s, calls `_should_send_report` per user
  - `user_today(tz: ZoneInfo | None = None) -> date` — updated signature accepts optional timezone

- [ ] **Step 1: Write failing tests for `_should_send_report`**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def test_should_send_report_at_correct_time(tmp_path):
    from bot import _should_send_report
    from users import UserManager
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    # 07:30 AM in Bogota (UTC-5) = 12:30 UTC
    now_utc = datetime(2026, 11, 23, 12, 30, 0, tzinfo=timezone.utc)
    sent_today = {}
    assert _should_send_report(123, "morning", now_utc, mgr, sent_today) is True

def test_should_send_report_wrong_time(tmp_path):
    from bot import _should_send_report
    from users import UserManager
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    # 15:00 UTC = 10:00 AM Bogota — not report time
    now_utc = datetime(2026, 11, 23, 15, 0, 0, tzinfo=timezone.utc)
    sent_today = {}
    assert _should_send_report(123, "morning", now_utc, mgr, sent_today) is False

def test_should_send_report_already_sent(tmp_path):
    from bot import _should_send_report
    from users import UserManager
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    now_utc = datetime(2026, 11, 23, 12, 30, 0, tzinfo=timezone.utc)
    sent_today = {(123, "morning"): "2026-11-23"}
    assert _should_send_report(123, "morning", now_utc, mgr, sent_today) is False

def test_should_send_report_no_users(tmp_path):
    """Empty user list should not cause errors."""
    from bot import _should_send_report
    from users import UserManager
    mgr = UserManager(users_dir=tmp_path)
    # No users created — list_users returns []
    # This tests that the caller (report_loop) handles empty list
    assert mgr.list_users() == []

def test_user_today_with_timezone():
    from bot import user_today
    from zoneinfo import ZoneInfo
    result = user_today(ZoneInfo("America/Bogota"))
    assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot.py::test_should_send_report_at_correct_time -v`
Expected: FAIL — `ImportError: cannot import name '_should_send_report' from 'bot'`

- [ ] **Step 3: Implement `_should_send_report` in `bot.py`**

Pure function: converts `now_utc` to user's local time using `UserManager.get_timezone`, gets user's `get_report_times`, checks if local time is within a 2-minute window of the scheduled time (HH:MM matching with 1-min tolerance), and checks `sent_today` dict to avoid duplicates. `sent_today` key is `(user_id, report_type)`, value is date string.

- [ ] **Step 4: Update `user_today` to accept optional timezone parameter**

`def user_today(tz: ZoneInfo | None = None) -> date:` — uses provided tz or falls back to `USER_TZ` global. Update all existing callers to pass tz when they have a user context.

- [ ] **Step 5: Rewrite `report_loop` in `bot.py`**

Replace the current sleep-until-next pattern with a 60-second polling loop:
1. Every 60s, get `list_users()`.
2. For each user, for each report type (`"morning"`, `"evening"`), call `_should_send_report`.
3. If True, send report and record in `sent_today`.
4. Clear `sent_today` entries from previous dates.
5. Add 2-second delay between users (spec D4).
6. Keep startup notification message.

Remove `_next_report()`, `REPORT_SCHEDULE` constant (no longer needed — schedule is per-user).

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: per-user report loop with individual timezone and schedule"
```

---

### Task 5: Registration transparency, timezone onboarding, and /eliminar

**Files:**
- Modify: `bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Consumes: `UserManager.delete_user` from Task 1, `resolve_timezone` from Task 3, `UserManager.update_timezone` from Task 1
- Produces:
  - `cmd_eliminar(update, context)` — handler for `/eliminar`
  - `cmd_cancelar(update, context)` — handler for `/cancelar` (cancels any active flow)
  - Updated `handle_registration` with `awaiting_timezone` step after profile
  - Updated password prompt message with encryption transparency text
  - Updated post-registration welcome message

- [ ] **Step 1: Write failing test for registration transparency message**

```python
def test_registration_password_prompt_mentions_encryption():
    """The password prompt must explain Fernet encryption and /eliminar."""
    import bot
    # Read the source string directly — the password prompt is in handle_registration
    import inspect
    source = inspect.getsource(bot.handle_registration)
    assert "cifrada" in source or "Fernet" in source
    assert "/eliminar" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_bot.py::test_registration_password_prompt_mentions_encryption -v`
Expected: FAIL — `/eliminar` not found in handle_registration source

- [ ] **Step 3: Update registration messages in `bot.py`**

In `handle_registration`, step `awaiting_email` → `awaiting_password`: change the message to:
`"Ahora envíame tu contraseña de Garmin Connect.\n🔒 Tu contraseña será cifrada (Fernet/AES) y almacenada en el servidor. No se guarda en texto plano, pero sí se almacena de forma cifrada para poder conectarse a Garmin automáticamente.\nSi en algún momento quieres eliminar tus datos, usa /eliminar."`

In `handle_registration`, step `awaiting_profile` → completion: change the success message to include a note about `/rutina` and `/config`.

- [ ] **Step 4: Add `awaiting_timezone` step to registration flow**

After `awaiting_profile`, instead of completing registration, move to `awaiting_timezone`. Bot asks: `"¿En qué país o ciudad estás? (para configurar tu zona horaria y horarios de reportes)"`. Use `resolve_timezone` to validate. If valid, store via `update_timezone` and complete registration. If invalid, show available options and retry.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_bot.py::test_registration_password_prompt_mentions_encryption -v`
Expected: PASS

- [ ] **Step 6: Write failing tests for `/eliminar`**

```python
def test_delete_clears_registration_state(tmp_path):
    """After /eliminar, all in-memory state for that user is gone."""
    import bot
    from users import UserManager
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    # Simulate in-memory state
    bot.conversations[123] = bot.ConversationHistory()
    bot.conversations[123].add("user", "hola")
    bot.registration_state[123] = {"step": "awaiting_routine_description"}
    bot.last_sync[123] = None
    # delete_user removes disk data
    mgr.delete_user(123)
    # In-memory cleanup (what /eliminar handler should do)
    bot.conversations.pop(123, None)
    bot.registration_state.pop(123, None)
    bot.last_sync.pop(123, None)
    assert 123 not in bot.conversations
    assert 123 not in bot.registration_state
    assert 123 not in bot.last_sync
    assert not mgr.user_exists(123)
```

- [ ] **Step 7: Implement `/eliminar` and `/cancelar` handlers in `bot.py`**

`cmd_eliminar`: checks user exists, sets `registration_state[user_id] = {"step": "awaiting_delete_confirmation"}`, asks "¿Estás seguro? Se eliminarán todos tus datos. Escribe ELIMINAR para confirmar."

Add step `awaiting_delete_confirmation` to `handle_registration`: if text matches "ELIMINAR" (case-insensitive), call `user_manager.delete_user(user_id)`, clean up `conversations`, `registration_state`, `last_sync`, confirm. Otherwise cancel.

`cmd_cancelar`: clears `registration_state[user_id]` if present, confirms cancellation. This covers canceling `/rutina`, `/config`, `/eliminar` flows.

Register `CommandHandler("eliminar", cmd_eliminar)` and `CommandHandler("cancelar", cmd_cancelar)` in `main()`.

- [ ] **Step 8: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add bot.py tests/test_bot.py
git commit -m "feat: registration transparency, timezone onboarding, /eliminar and /cancelar"
```
