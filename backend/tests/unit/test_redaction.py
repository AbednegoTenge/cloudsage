import logging

from app.core.logging import RedactingFilter, redact


def test_redacts_access_key_ids():
    assert "AKIAABCDEFGHIJKLMNOP" not in redact("key=AKIAABCDEFGHIJKLMNOP")
    assert "ASIAABCDEFGHIJKLMNOP" not in redact("ASIAABCDEFGHIJKLMNOP used")


def test_redacts_secret_and_token_values():
    out = redact('{"SecretAccessKey": "abc/123+xyz", "SessionToken": "tok"}')
    assert "abc/123+xyz" not in out and 'tok"' not in out
    assert "[REDACTED]" in out


def test_redacts_bearer_tokens():
    assert "eyJhbGci" not in redact("Authorization: Bearer eyJhbGci.payload.sig")


def test_filter_scrubs_log_records():
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "creds %s", ("AKIAABCDEFGHIJKLMNOP",), None
    )
    RedactingFilter().filter(record)
    assert "AKIA" not in record.getMessage()
