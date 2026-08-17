"""Tests for emitter's pure core, runnable with the stdlib alone: python3 test_emitter.py.

The fixtures are trimmed real response shapes; every assertion mirrors a rule
from the Vantage spec (see the skip-rule table in README.md).
"""
from __future__ import annotations

import gzip
import json
import re

from emitter import (
    TelemetryWriter,
    ndjson_gz,
    object_key,
    record_from_anthropic,
    record_from_openai,
    records_by_day,
    validate_record,
)

TS = "2026-08-12T12:30:45.123456Z"

OPENAI_CHAT = {
    "id": "chatcmpl-AbC123",
    "model": "gpt-4o-2024-08-06",
    "service_tier": "default",
    "usage": {
        "prompt_tokens": 2129,
        "completion_tokens": 112,
        "total_tokens": 2241,
        "prompt_tokens_details": {"cached_tokens": 572},
    },
}

OPENAI_RESPONSES_API = {
    "id": "resp_XyZ789",
    "model": "gpt-4o-2024-08-06",
    "usage": {
        "input_tokens": 900,
        "output_tokens": 40,
        "input_tokens_details": {"cached_tokens": 100},
    },
}

ANTHROPIC_MSG = {
    "id": "msg_01AbCd",
    "model": "claude-sonnet-4-6",
    "usage": {
        "input_tokens": 1268,
        "output_tokens": 312,
        "cache_read_input_tokens": 572,
        "cache_creation_input_tokens": 0,
    },
}


def test_openai_chat_completion_maps() -> None:
    """OpenAI chat usage maps straight through; prompt tokens already include cache."""
    record = record_from_openai(OPENAI_CHAT, TS, tags={"team": "growth"})
    assert record["event_id"] == "chatcmpl-AbC123"
    assert record["provider"] == "openai"
    assert record["service_tier"] == "default"
    assert record["usage"] == {
        "input_tokens": 2129,
        "output_tokens": 112,
        "cache_read_input_tokens": 572,
    }
    assert validate_record(record) == []


def test_openai_responses_api_maps() -> None:
    """The Responses API field names coalesce to the same record shape."""
    record = record_from_openai(OPENAI_RESPONSES_API, TS)
    assert record["usage"] == {
        "input_tokens": 900,
        "output_tokens": 40,
        "cache_read_input_tokens": 100,
    }
    assert validate_record(record) == []


def test_anthropic_cache_tokens_are_added_back() -> None:
    """Anthropic input_tokens excludes cache; the spec total must include it."""
    record = record_from_anthropic(ANTHROPIC_MSG, TS)
    assert record["usage"]["input_tokens"] == 1268 + 572
    assert record["usage"]["cache_read_input_tokens"] == 572
    assert "cache_write_input_tokens" not in record["usage"]
    assert validate_record(record) == []


def test_validate_catches_the_spec_skip_rules() -> None:
    """Each spec skip rule produces a named problem."""
    assert validate_record({}) != []
    good = record_from_openai(OPENAI_CHAT, TS)

    bad_provider = dict(good, provider="cohere")
    assert any("provider" in p for p in validate_record(bad_provider))

    bad_status = dict(good, status="error")
    assert any("status" in p for p in validate_record(bad_status))

    bad_timestamp = dict(good, timestamp="1754870400")
    assert any("timestamp" in p for p in validate_record(bad_timestamp))

    string_counts = dict(good, usage={"input_tokens": "2129"})
    assert any("JSON integers" in p for p in validate_record(string_counts))

    zero_usage = dict(good, usage={"input_tokens": 0, "output_tokens": 0})
    assert any("positive integer" in p for p in validate_record(zero_usage))


def test_object_key_matches_vantage_layout() -> None:
    """Keys must be <prefix>/YYYY/MM/DD/<flat-name>.jsonl.gz."""
    key = object_key("2026-08-12", "abc123", "llm")
    assert key == "llm/2026/08/12/abc123.jsonl.gz"
    assert re.fullmatch(r"(.*/)?\d{4}/\d{2}/\d{2}/[^/]+\.jsonl\.gz", key)


def test_ndjson_round_trips() -> None:
    """Output is gzip NDJSON: one JSON object per line, no outer array."""
    record = record_from_openai(OPENAI_CHAT, TS)
    lines = gzip.decompress(ndjson_gz([record, record])).decode().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "chatcmpl-AbC123"


def test_records_group_by_utc_day() -> None:
    """Partitioning follows the record timestamp's UTC date."""
    a = record_from_openai(OPENAI_CHAT, "2026-08-12T23:59:58.000000Z")
    b = record_from_openai(OPENAI_CHAT, "2026-08-13T00:00:02.000000Z")
    assert sorted(records_by_day([a, b])) == ["2026-08-12", "2026-08-13"]


def test_openai_streaming_final_chunk_shape_maps() -> None:
    """A record can be built from a stream's final usage chunk (id + model + usage)."""
    final_chunk_shape = {
        "id": "chatcmpl-Stream1",
        "model": "gpt-4o-2024-08-06",
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 9,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }
    record = record_from_openai(final_chunk_shape, TS)
    assert record["usage"] == {"input_tokens": 50, "output_tokens": 9}
    assert validate_record(record) == []


class _FlakyWriter(TelemetryWriter):
    """Writer whose first write attempt fails, for retry-semantics tests."""

    def __init__(self) -> None:
        """Start in failing mode with no destination."""
        super().__init__(bucket=None, dry_run_dir=None)
        self.fail = True
        self.written: list[str] = []

    def _write(self, key: str, body: bytes) -> None:
        """Record the key, or raise while in failing mode."""
        if self.fail:
            raise OSError("simulated S3 outage")
        self.written.append(key)


def test_flush_retains_buffer_on_failure_and_retries_cleanly() -> None:
    """A failed flush keeps every record; the retry writes them all."""
    writer = _FlakyWriter()
    writer.add(record_from_openai(OPENAI_CHAT, TS))
    writer.add(record_from_anthropic(ANTHROPIC_MSG, TS))

    try:
        writer.flush()
        raise AssertionError("flush should have raised")
    except OSError:
        pass

    writer.fail = False
    keys = writer.flush()
    assert len(keys) == 1 and len(writer.written) == 1
    assert writer.flush() == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok   {test.__name__}")
    print(f"PASS {len(tests)} tests")
