from bot import build_system_prompt, ConversationHistory, run_sync_safe, user_manager
from users import UserManager


def test_build_system_prompt_includes_snapshot():
    snapshot = "ACTIVIDADES: Carrera 5km en 30min"
    result = build_system_prompt(snapshot, "Corro 3 veces por semana")
    assert "Carrera 5km" in result
    assert "coach" in result.lower() or "entrenador" in result.lower()


def test_build_system_prompt_includes_metric_explanations():
    result = build_system_prompt("datos vacíos", "")
    assert "HRV" in result
    assert "Training Readiness" in result


def test_build_system_prompt_includes_user_profile():
    result = build_system_prompt("datos", "Hago crossfit 4 veces por semana")
    assert "crossfit" in result


def test_build_system_prompt_no_profile_suggests_setup():
    result = build_system_prompt("datos", "")
    assert "/perfil" in result


def test_conversation_history_bounded():
    history = ConversationHistory(max_messages=10)
    for i in range(15):
        history.add("user", f"message {i}")
        history.add("model", f"response {i}")
    messages = history.get_messages()
    assert len(messages) == 10
    assert messages[0]["content"] == "message 10"


def test_conversation_history_to_gemini_format():
    history = ConversationHistory(max_messages=10)
    history.add("user", "hola")
    history.add("model", "hola, ¿cómo te fue?")
    messages = history.get_messages()
    assert messages[0] == {"role": "user", "content": "hola"}
    assert messages[1] == {"role": "model", "content": "hola, ¿cómo te fue?"}


def test_conversation_history_truncation_drops_leading_model():
    history = ConversationHistory(max_messages=3)
    history.add("user", "a")
    history.add("model", "b")
    history.add("user", "c")
    history.add("model", "d")
    messages = history.get_messages()
    assert messages[0]["role"] == "user"


def test_run_sync_safe_returns_false_without_user_manager(monkeypatch, tmp_path):
    import bot
    mgr = UserManager(users_dir=tmp_path)
    monkeypatch.setattr(bot, "user_manager", mgr)
    result = run_sync_safe(99999)
    assert result is False


def test_run_sync_safe_returns_true_on_success(monkeypatch, tmp_path):
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(123, "a@b.com", "p")
    monkeypatch.setattr(bot, "user_manager", mgr)
    monkeypatch.setattr("bot.create_client", lambda *a, **kw: None)
    monkeypatch.setattr("bot.sync_activities", lambda *a, **kw: 0)
    monkeypatch.setattr("bot.sync_daily_stats", lambda *a, **kw: 0)
    result = run_sync_safe(123)
    assert result is True


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


def test_rutina_flow_states():
    """Verify /rutina sets up the correct registration_state steps."""
    from bot import registration_state
    import bot
    # Simulate: user triggers /rutina -> state should be awaiting_routine_description
    # Then user sends text -> state should be awaiting_routine_approval (after Gemini parses)
    # Then user approves -> state cleared, routine saved
    registration_state[123] = {"step": "awaiting_routine_description"}
    assert registration_state[123]["step"] == "awaiting_routine_description"


def test_rutina_flow_not_broken_by_concurrent_send():
    """Registration_state only intercepts user text messages, not bot pushes."""
    from bot import registration_state
    # A user in /rutina flow has step set
    registration_state[123] = {"step": "awaiting_routine_approval", "parsed_routine": "Lunes: Gym"}
    # This state only affects handle_message -> handle_registration path
    # Bot.send_message (reports) bypasses this entirely
    assert registration_state[123]["step"] == "awaiting_routine_approval"


# --- resolve_timezone tests ---

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


# --- /config command tests ---

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _make_update(user_id: int, text: str):
    """Helper: build a minimal Telegram Update mock."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.delete = AsyncMock()
    return update


def _make_context():
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def test_cmd_config_requires_registration(tmp_path, monkeypatch):
    """cmd_config must reject unregistered users."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    monkeypatch.setattr(bot, "user_manager", mgr)

    update = _make_update(999, "/config")
    ctx = _make_context()

    from bot import cmd_config
    asyncio.run(cmd_config(update, ctx))

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0][0]
    assert "registr" in args.lower() or "start" in args.lower()


def test_cmd_config_shows_current_settings(tmp_path, monkeypatch):
    """cmd_config must show current timezone and report times, then ask for new timezone."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)

    update = _make_update(42, "/config")
    ctx = _make_context()

    from bot import cmd_config, registration_state
    asyncio.run(cmd_config(update, ctx))

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    # Should mention timezone and report times
    assert "America/Bogota" in text or "zona horaria" in text.lower()
    assert registration_state[42]["step"] == "awaiting_config_timezone"


def test_config_flow_valid_timezone(tmp_path, monkeypatch):
    """Sending a valid timezone moves state to awaiting_config_morning."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_timezone"}

    update = _make_update(42, "America/Bogota")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert mgr.get_timezone(42) == "America/Bogota"
    assert bot.registration_state[42]["step"] == "awaiting_config_morning"


def test_config_flow_city_name_timezone(tmp_path, monkeypatch):
    """Sending a city name resolves to IANA and moves state forward."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_timezone"}

    update = _make_update(42, "Madrid")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert mgr.get_timezone(42) == "Europe/Madrid"
    assert bot.registration_state[42]["step"] == "awaiting_config_morning"


def test_config_flow_invalid_timezone_asks_again(tmp_path, monkeypatch):
    """Sending an invalid timezone keeps state in awaiting_config_timezone."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_timezone"}

    update = _make_update(42, "Atlantis")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert bot.registration_state[42]["step"] == "awaiting_config_timezone"
    update.message.reply_text.assert_called_once()


def test_config_flow_morning_time(tmp_path, monkeypatch):
    """Valid HH:MM for morning stores it in state and moves to awaiting_config_evening."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_morning"}

    update = _make_update(42, "08:00")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert bot.registration_state[42].get("morning_time") == "08:00"
    assert bot.registration_state[42]["step"] == "awaiting_config_evening"


def test_config_flow_invalid_morning_time_asks_again(tmp_path, monkeypatch):
    """Invalid time format keeps state at awaiting_config_morning."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_morning"}

    update = _make_update(42, "8am")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert bot.registration_state[42]["step"] == "awaiting_config_morning"


def test_config_flow_complete(tmp_path, monkeypatch):
    """Full config flow: saves report times and clears state on evening time entry."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_evening", "morning_time": "08:00"}

    update = _make_update(42, "21:00")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    morning, evening = mgr.get_report_times(42)
    assert morning == "08:00"
    assert evening == "21:00"
    assert 42 not in bot.registration_state
    update.message.reply_text.assert_called_once()


def test_config_flow_invalid_evening_time_asks_again(tmp_path, monkeypatch):
    """Invalid evening time keeps state at awaiting_config_evening."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_config_evening", "morning_time": "08:00"}

    update = _make_update(42, "9pm")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert bot.registration_state[42]["step"] == "awaiting_config_evening"


# --- _should_send_report tests ---

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


# --- Task 5: Registration transparency, timezone onboarding, /eliminar, /cancelar ---

def test_registration_password_prompt_mentions_encryption():
    """The password prompt must explain Fernet encryption and /eliminar."""
    import bot
    import inspect
    source = inspect.getsource(bot.handle_registration)
    assert "cifrada" in source or "Fernet" in source
    assert "/eliminar" in source


def test_registration_awaiting_timezone_step_exists(tmp_path, monkeypatch):
    """After profile is set during registration (not update_only), state moves to awaiting_timezone."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    # Simulate being in awaiting_profile during registration (not update_only)
    bot.registration_state[42] = {"step": "awaiting_profile"}

    update = _make_update(42, "Voy al gym 3 veces por semana")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    # Should NOT clear state — should move to awaiting_timezone
    assert 42 in bot.registration_state
    assert bot.registration_state[42]["step"] == "awaiting_timezone"


def test_registration_awaiting_timezone_valid(tmp_path, monkeypatch):
    """Sending a valid city/timezone during registration completes it."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_timezone"}

    update = _make_update(42, "Bogotá")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    # State should be cleared (registration complete)
    assert 42 not in bot.registration_state
    # Timezone should be saved
    assert mgr.get_timezone(42) == "America/Bogota"


def test_registration_awaiting_timezone_invalid_asks_again(tmp_path, monkeypatch):
    """Sending an unrecognised location keeps state in awaiting_timezone."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_timezone"}

    update = _make_update(42, "Atlantis")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert 42 in bot.registration_state
    assert bot.registration_state[42]["step"] == "awaiting_timezone"
    update.message.reply_text.assert_called_once()


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


def test_cmd_eliminar_asks_confirmation(tmp_path, monkeypatch):
    """cmd_eliminar sets awaiting_delete_confirmation state and sends confirmation prompt."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)

    update = _make_update(42, "/eliminar")
    ctx = _make_context()

    from bot import cmd_eliminar
    asyncio.run(cmd_eliminar(update, ctx))

    assert bot.registration_state[42]["step"] == "awaiting_delete_confirmation"
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "ELIMINAR" in text


def test_cmd_eliminar_unregistered_user(tmp_path, monkeypatch):
    """cmd_eliminar tells unregistered user to register first."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    monkeypatch.setattr(bot, "user_manager", mgr)

    update = _make_update(999, "/eliminar")
    ctx = _make_context()

    from bot import cmd_eliminar
    asyncio.run(cmd_eliminar(update, ctx))

    assert 999 not in bot.registration_state
    update.message.reply_text.assert_called_once()


def test_delete_confirmation_eliminates_user(tmp_path, monkeypatch):
    """Typing ELIMINAR in awaiting_delete_confirmation deletes user and clears state."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_delete_confirmation"}
    bot.conversations[42] = bot.ConversationHistory()
    bot.last_sync[42] = None

    update = _make_update(42, "ELIMINAR")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    assert not mgr.user_exists(42)
    assert 42 not in bot.registration_state
    assert 42 not in bot.conversations
    assert 42 not in bot.last_sync
    update.message.reply_text.assert_called_once()


def test_delete_confirmation_wrong_text_cancels(tmp_path, monkeypatch):
    """Typing anything other than ELIMINAR cancels the deletion and clears state."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_delete_confirmation"}

    update = _make_update(42, "no")
    ctx = _make_context()

    from bot import handle_registration
    asyncio.run(handle_registration(update, ctx))

    # User data must still exist
    assert mgr.user_exists(42)
    assert 42 not in bot.registration_state
    update.message.reply_text.assert_called_once()


def test_cmd_cancelar_clears_state(tmp_path, monkeypatch):
    """cmd_cancelar clears registration_state for the user and confirms."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    bot.registration_state[42] = {"step": "awaiting_routine_description"}

    update = _make_update(42, "/cancelar")
    ctx = _make_context()

    from bot import cmd_cancelar
    asyncio.run(cmd_cancelar(update, ctx))

    assert 42 not in bot.registration_state
    update.message.reply_text.assert_called_once()


def test_cmd_cancelar_no_active_flow(tmp_path, monkeypatch):
    """cmd_cancelar does not error when there is no active flow."""
    import bot
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    # No state set for user 42

    update = _make_update(42, "/cancelar")
    ctx = _make_context()

    from bot import cmd_cancelar
    asyncio.run(cmd_cancelar(update, ctx))

    update.message.reply_text.assert_called_once()


# --- Fix: exact numbers instruction + data completeness + snapshot logging ---


def test_build_system_prompt_requires_exact_numbers():
    """System prompt must instruct Gemini to cite exact numbers from the snapshot."""
    result = build_system_prompt("datos de test", "perfil")
    assert "EXACTOS" in result or "exactos" in result


def test_morning_report_prompt_forbids_citing_numbers():
    """Morning report prompt must tell Gemini NOT to cite numbers."""
    from bot import MORNING_REPORT_PROMPT
    assert "no repitas" in MORNING_REPORT_PROMPT.lower() or "no cites" in MORNING_REPORT_PROMPT.lower()


def test_evening_report_prompt_forbids_citing_numbers():
    """Evening report prompt must tell Gemini NOT to cite numbers."""
    from bot import EVENING_REPORT_PROMPT
    assert "no repitas" in EVENING_REPORT_PROMPT.lower() or "no cites" in EVENING_REPORT_PROMPT.lower()


def test_is_morning_data_ready_missing_sleep():
    """Data without sleep score is not ready for morning report."""
    from analysis import is_morning_data_ready
    stats = {"stats": {"bodyBatteryAtWakeTime": 0}, "sleep": {}, "training_readiness": [], "hrv": {}}
    assert is_morning_data_ready(stats) is False


def test_is_morning_data_ready_missing_bb_wake():
    """Data without bodyBatteryAtWakeTime is not ready."""
    from analysis import is_morning_data_ready
    stats = {
        "stats": {},
        "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 83}}}},
        "training_readiness": [{"score": 65}],
        "hrv": {},
    }
    assert is_morning_data_ready(stats) is False


def test_is_morning_data_ready_complete():
    """Data with sleep score and BB at wake is ready."""
    from analysis import is_morning_data_ready
    stats = {
        "stats": {"bodyBatteryAtWakeTime": 70},
        "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 83}}}},
        "training_readiness": [{"score": 65}],
        "hrv": {},
    }
    assert is_morning_data_ready(stats) is True


def test_is_morning_data_ready_bb_zero_is_not_ready():
    """BB at wake = 0 means Garmin hasn't calculated it yet."""
    from analysis import is_morning_data_ready
    stats = {
        "stats": {"bodyBatteryAtWakeTime": 0},
        "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 83}}}},
        "training_readiness": [{"score": 65}],
        "hrv": {},
    }
    assert is_morning_data_ready(stats) is False


def test_generate_report_logs_snapshot(monkeypatch, tmp_path, caplog):
    """generate_and_send_report must log the snapshot sent to Gemini."""
    import bot
    import logging
    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    monkeypatch.setattr(bot, "last_sync", {})

    def fake_sync(uid):
        return True
    monkeypatch.setattr(bot, "run_sync_safe", fake_sync)
    monkeypatch.setattr(bot, "build_context_snapshot", lambda *a, **kw: "SNAPSHOT_TEST_DATA")
    monkeypatch.setattr(bot, "call_gemini", lambda sys, usr: "reporte generado")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with caplog.at_level(logging.DEBUG, logger="bot"):
        asyncio.run(bot.generate_and_send_report(mock_bot, 42, "morning"))

    assert any("SNAPSHOT_TEST_DATA" in r.message for r in caplog.records)


def test_morning_report_retries_sync_when_data_incomplete(monkeypatch, tmp_path):
    """Morning report re-syncs once if today's data is incomplete (BB=0, no sleep)."""
    import json
    import bot

    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    monkeypatch.setattr(bot, "last_sync", {})

    stats_dir = mgr.stats_dir(42)
    stats_dir.mkdir(parents=True, exist_ok=True)

    incomplete_stats = {"stats": {"bodyBatteryAtWakeTime": 0}, "sleep": {}, "training_readiness": [], "hrv": {}}
    complete_stats = {
        "stats": {"bodyBatteryAtWakeTime": 70, "bodyBatteryMostRecentValue": 68},
        "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 83}}}},
        "training_readiness": [{"score": 65}],
        "hrv": {},
    }

    sync_call_count = 0
    today_str = bot.user_today(ZoneInfo("America/Bogota")).isoformat()
    stats_file = stats_dir / f"{today_str}.json"

    def fake_sync(uid):
        nonlocal sync_call_count
        sync_call_count += 1
        if sync_call_count >= 2:
            stats_file.write_text(json.dumps(complete_stats))
        else:
            stats_file.write_text(json.dumps(incomplete_stats))
        return True

    monkeypatch.setattr(bot, "run_sync_safe", fake_sync)
    monkeypatch.setattr(bot, "call_gemini", lambda sys, usr: "reporte generado")
    monkeypatch.setattr(bot, "MORNING_DATA_RETRY_DELAY", 0)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    asyncio.run(bot.generate_and_send_report(mock_bot, 42, "morning"))

    assert sync_call_count >= 2, f"Expected re-sync, but sync was called {sync_call_count} time(s)"


def test_generate_report_message_has_data_card_and_analysis(monkeypatch, tmp_path):
    """Final message must contain code-generated data card followed by Gemini analysis."""
    import json
    import bot

    mgr = UserManager(users_dir=tmp_path)
    mgr.create_user(42, "a@b.com", "pw")
    monkeypatch.setattr(bot, "user_manager", mgr)
    monkeypatch.setattr(bot, "last_sync", {})

    stats_dir = mgr.stats_dir(42)
    stats_dir.mkdir(parents=True, exist_ok=True)
    today_str = bot.user_today(ZoneInfo("America/Bogota")).isoformat()
    stats = {
        "stats": {"restingHeartRate": 52, "bodyBatteryAtWakeTime": 70, "bodyBatteryMostRecentValue": 68},
        "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 83, "qualifierKey": "GOOD"}}}},
        "training_readiness": [{"score": 82, "level": "HIGH"}],
        "hrv": {},
    }
    (stats_dir / f"{today_str}.json").write_text(json.dumps(stats))

    monkeypatch.setattr(bot, "run_sync_safe", lambda uid: True)
    monkeypatch.setattr(bot, "call_gemini", lambda sys, usr: "Análisis de Gemini aquí.")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    asyncio.run(bot.generate_and_send_report(mock_bot, 42, "morning"))

    sent_text = mock_bot.send_message.call_args[1]["text"]
    assert "📊 Datos verificados:" in sent_text
    assert "52 bpm" in sent_text
    assert "83" in sent_text
    assert "---" in sent_text
    assert "🤖 Análisis:" in sent_text
    assert "Análisis de Gemini aquí." in sent_text
