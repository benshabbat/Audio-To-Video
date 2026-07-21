from core.error_utils import safe_error


def test_redacts_google_style_api_key():
    key = "AIza" + "A" * 35
    result = safe_error(Exception(f"call failed: https://example.com/v1?x={key}"))
    assert key not in result
    assert "[REDACTED]" in result


def test_redacts_key_query_param():
    result = safe_error(Exception("GET https://api.example.com/x?key=super-secret-value failed"))
    assert "super-secret-value" not in result
    assert "?key=[REDACTED]" in result


def test_redacts_api_key_assignment_style():
    result = safe_error(Exception('config error api_key="sk-1234567890abcdef" invalid'))
    assert "sk-1234567890abcdef" not in result


def test_leaves_unrelated_text_untouched():
    assert safe_error(Exception("connection timed out after 30 seconds")) == "connection timed out after 30 seconds"
