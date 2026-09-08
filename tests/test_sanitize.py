from annals.sanitize import PLACEHOLDER, dump_sanitized, scrub


def test_key_name_redacts_token():
    hits: list[str] = []
    out = scrub({"api_token": "abcdefghijklmnopqrstuvwxyz"}, hits)
    assert out["api_token"] == PLACEHOLDER
    assert "api_token" in hits


def test_otel_header_without_token_in_key_name():
    """Regression: a Bearer token lived under OTEL_EXPORTER_OTLP_HEADERS."""
    src = {
        "env": {
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer abcdefghijklmnopqr"
        }
    }
    out = scrub(src)
    assert PLACEHOLDER in out["env"]["OTEL_EXPORTER_OTLP_HEADERS"]
    assert "abcdefghijklmnopqr" not in dump_sanitized(src)


def test_github_pat_in_value():
    out = scrub({"note": "export GH=ghp_abcdefghijklmnopqrstuvwxyz012345"})
    assert PLACEHOLDER in out["note"]


def test_short_strings_survive():
    src = {"model": "opus", "name": "token-lite"}
    assert scrub(src) == src


def test_structure_preserved():
    src = {"permissions": {"allow": ["Bash"]}, "api_key": "x" * 20}
    out = scrub(src)
    assert out["permissions"] == src["permissions"]
    assert out["api_key"] == PLACEHOLDER
