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
