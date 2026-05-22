from app.services.ai import AiService


def test_ai_service_has_fallback_without_key(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.settings.openai_api_key", None)
    service = AiService()
    result = service.polish_markdown("# Test")
    assert result.html
    assert result.title
