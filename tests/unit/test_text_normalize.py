from carcase_ai_moderation.application.text import normalize_text


def test_normalize_text_basic() -> None:
    assert normalize_text("  Hello   World ") == "hello world"
