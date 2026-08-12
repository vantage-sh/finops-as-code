"""Build and ship Vantage Token Cost Allocation records from LLM API responses.

Everything above TelemetryWriter is pure (response data in, record out) and
testable with plain dicts; TelemetryWriter is the shell that buffers records
and writes date-partitioned .jsonl.gz objects to S3 or a local directory.
Spec: https://docs.vantage.sh/custom_telemetry
"""
from __future__ import annotations

import gzip
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ACCEPTED_PROVIDERS = {
    "openai", "anthropic", "aws", "bedrock",
    "gcp", "gemini", "google", "vertex",
    "azure", "azure_openai", "azure-openai",
}

USAGE_FIELDS = (
    "input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_write_input_tokens",
)


# --- core: pure functions, data in, data out ---------------------------------

def record_from_openai(response: dict, timestamp: str, tags: dict | None = None) -> dict:
    """Return a spec record from an OpenAI response dict (chat completions or responses API)."""
    usage = response.get("usage") or {}
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    record = {
        "event_id": response["id"],
        "timestamp": timestamp,
        "provider": "openai",
        "model": response["model"],
        # OpenAI's prompt/input token count already includes cached tokens,
        # which is exactly the inclusive semantics the spec expects.
        "usage": positive_usage({
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "cache_read_input_tokens": details.get("cached_tokens"),
        }),
    }
    if response.get("service_tier"):
        record["service_tier"] = response["service_tier"]
    if tags:
        record["tags"] = tags
    return record


def record_from_anthropic(response: dict, timestamp: str, tags: dict | None = None) -> dict:
    """Return a spec record from an Anthropic Messages API response dict."""
    usage = response.get("usage") or {}
    cache_read = usage.get("cache_read_input_tokens") or 0
    cache_write = usage.get("cache_creation_input_tokens") or 0
    record = {
        "event_id": response["id"],
        "timestamp": timestamp,
        "provider": "anthropic",
        "model": response["model"],
        # Anthropic's input_tokens EXCLUDES cached tokens; the spec's
        # input_tokens is the inclusive total, so add the cache counts back.
        # Sending Anthropic's raw value would misallocate the cache-priced
        # portion of spend.
        "usage": positive_usage({
            "input_tokens": (usage.get("input_tokens") or 0) + cache_read + cache_write,
            "output_tokens": usage.get("output_tokens"),
            "cache_read_input_tokens": cache_read,
            "cache_write_input_tokens": cache_write,
        }),
    }
    if tags:
        record["tags"] = tags
    return record


def positive_usage(entries: dict) -> dict:
    """Return only the usage entries that are positive integers."""
    return {
        k: v for k, v in entries.items()
        if isinstance(v, int) and not isinstance(v, bool) and v > 0
    }


def validate_record(record: dict) -> list[str]:
    """Return the reasons Vantage would skip this record; empty means ingestible."""
    problems = []
    problems += [
        f"{field} is missing or blank"
        for field in ("event_id", "timestamp", "provider", "model")
        if not str(record.get(field, "")).strip()
    ]
    if not parses_as_utc_timestamp(str(record.get("timestamp", ""))):
        problems.append("timestamp is not ISO 8601 UTC with a Z suffix")
    if str(record.get("provider", "")).strip().lower() not in ACCEPTED_PROVIDERS:
        problems.append(f"provider {record.get('provider')!r} is not an accepted value")
    status = record.get("status")
    if status is not None and str(status).strip().lower() not in ("", "success"):
        problems.append(f"status {status!r} is not 'success'; the record will be skipped")
    problems += usage_problems(record.get("usage"))
    return problems


def usage_problems(usage: object) -> list[str]:
    """Return every way the usage block would fail ingestion."""
    if not isinstance(usage, dict):
        return ["usage is not a JSON object"]
    strings = [k for k in USAGE_FIELDS if isinstance(usage.get(k), str)]
    problems = [
        f"usage.{k} is a string; counts must be JSON integers or they are dropped"
        for k in strings
    ]
    if not positive_usage({k: usage.get(k) for k in USAGE_FIELDS}):
        problems.append("no usage field is a positive integer")
    return problems


def parses_as_utc_timestamp(value: str) -> bool:
    """Return True when value is ISO 8601 with an explicit Z suffix."""
    if not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def records_by_day(records: list[dict]) -> dict:
    """Return records grouped by the UTC date of their timestamp."""
    days: dict = {}
    for record in records:
        days.setdefault(record["timestamp"][:10], []).append(record)
    return days


def object_key(day: str, batch_id: str, prefix: str) -> str:
    """Return the date-partitioned key Vantage's reader expects for a YYYY-MM-DD day."""
    return f"{prefix}/{day.replace('-', '/')}/{batch_id}.jsonl.gz"


def ndjson_gz(records: list[dict]) -> bytes:
    """Return the records gzip-compressed, one JSON object per line, no outer array."""
    lines = "".join(json.dumps(record) + "\n" for record in records)
    return gzip.compress(lines.encode("utf-8"))


# --- shell: clock, buffering, S3 ---------------------------------------------

def utc_now_iso() -> str:
    """Return the current UTC time in the spec's ISO 8601 Z format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class TelemetryWriter:
    """Buffers records and writes them as date-partitioned .jsonl.gz objects.

    Thread-safe: add() and flush() may be called from multiple threads (for
    example FastAPI's threadpool plus a background flusher). flush() is safe
    to retry after a failure: the batch goes back into the buffer, and a
    retry that re-writes an already-written day is harmless because Vantage
    keeps one record per event_id per day.
    """

    def __init__(self, bucket: str | None, prefix: str = "llm",
                 dry_run_dir: str | None = None) -> None:
        """Write to the S3 bucket when set, else to dry_run_dir for inspection."""
        self._bucket = bucket
        self._prefix = prefix
        self._dry_run_dir = dry_run_dir
        self._lock = threading.Lock()
        self._records: list[dict] = []

    def add(self, record: dict) -> None:
        """Buffer one record, raising ValueError on anything Vantage would skip."""
        problems = validate_record(record)
        if problems:
            raise ValueError("record would be skipped: " + "; ".join(problems))
        with self._lock:
            self._records.append(record)

    def flush(self) -> list[str]:
        """Write one object per UTC day and return the keys written."""
        with self._lock:
            batch, self._records = self._records, []
        keys = []
        try:
            for day, records in records_by_day(batch).items():
                key = object_key(day, uuid4().hex, self._prefix)
                self._write(key, ndjson_gz(records))
                keys.append(key)
        except Exception:
            with self._lock:
                self._records[:0] = batch
            raise
        return keys

    def _write(self, key: str, body: bytes) -> None:
        """Put one object to S3 or the local dry-run directory."""
        if self._dry_run_dir is not None:
            path = Path(self._dry_run_dir) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            return
        import boto3
        boto3.client("s3").put_object(Bucket=self._bucket, Key=key, Body=body)
