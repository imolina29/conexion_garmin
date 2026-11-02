from bot import build_system_prompt, ConversationHistory, run_sync_safe


class MockClient:
    pass


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


def test_conversation_history_bounded():
    history = ConversationHistory(max_messages=10)
    for i in range(15):
        history.add("user", f"message {i}")
        history.add("assistant", f"response {i}")
    messages = history.get_messages()
    assert len(messages) == 10
    assert messages[0]["content"] == "message 10"


def test_conversation_history_to_claude_format():
    history = ConversationHistory(max_messages=10)
    history.add("user", "hola")
    history.add("assistant", "hola, ¿cómo te fue?")
    messages = history.get_messages()
    assert messages[0] == {"role": "user", "content": "hola"}
    assert messages[1] == {"role": "assistant", "content": "hola, ¿cómo te fue?"}


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
