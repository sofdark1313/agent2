from app.services.ai import AiService


def test_ai_service_has_fallback_without_key(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.settings.ai_api_key", None)
    monkeypatch.setattr("app.services.ai.settings.ai_base_url", None)
    monkeypatch.setattr("app.services.ai.settings.ai_model_name", None)
    service = AiService()
    result = service.polish_markdown("# Test")
    assert result.html
    assert result.title
