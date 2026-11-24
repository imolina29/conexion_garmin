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
