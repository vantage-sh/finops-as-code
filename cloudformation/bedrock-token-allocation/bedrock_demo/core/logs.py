"""Pure native Bedrock log paths, records, and source connection values."""
from __future__ import annotations

import gzip
import json
import re
from datetime import date, timedelta

REQUIRED_RECORD_FIELDS = ("schemaType", "timestamp", "accountId", "region",
                          "requestId", "operation", "modelId")


def log_prefix(account_id: str, region: str, key_prefix: str = "") -> str:
    """Return the S3 prefix Bedrock writes to and Vantage reads from, with trailing slash."""
    base = f"AWSLogs/{account_id}/BedrockModelInvocationLogs/{region}/"
    return f"{key_prefix.strip('/')}/{base}" if key_prefix.strip("/") else base


def vantage_connect_values(bucket: str, account_id: str, region: str,
                           key_prefix: str = "") -> dict:
    """Return the original bucket and its reference scan values for native Vantage."""
    return {
        "bucket": bucket,
        "prefix": log_prefix(account_id, region, key_prefix),
        "region": region,
    }


def object_key_pattern(account_id: str, region: str, key_prefix: str = "") -> str:
    """Return a regex matching invocation-record keys only, never the data/ payload objects."""
    prefix = re.escape(log_prefix(account_id, region, key_prefix))
    # YYYY/MM/DD/HH/<one filename>: [^/]+ is what excludes the data/ subtree,
    # where Bedrock puts request and response bodies over 100 KB.
    return rf"{prefix}\d{{4}}/\d{{2}}/\d{{2}}/\d{{2}}/[^/]+\.json\.gz"


def day_prefixes(prefix: str, today: date, days: int) -> list[str]:
    """Return the S3 prefixes for the last N days, newest first."""
    return [f"{prefix}{(today - timedelta(days=offset)):%Y/%m/%d}/" for offset in range(days)]


def record_problems(record: object) -> list[str]:
    """Return basic native-log readiness problems, not a guarantee of CUR matching."""
    if not isinstance(record, dict):
        return ["record is not a JSON object"]
    problems = [
        f"{field} is missing or blank"
        for field in REQUIRED_RECORD_FIELDS
        if not str(record.get(field) or "").strip()
    ]
    schema = record.get("schemaType")
    if schema and schema != "ModelInvocationLog":
        problems.append(f"schemaType {schema!r} is filtered out; only ModelInvocationLog rows join")
    return problems


def record_warnings(record: object) -> list[str]:
    """Return metadata gaps that reduce the available allocation dimensions."""
    if not isinstance(record, dict):
        return []
    if record.get("requestMetadata"):
        return []
    return ["no requestMetadata: spend still splits by principal and model, "
            "but none of your team/app/env tags (see the README section)"]


def records_from_gz(body: bytes) -> list[dict]:
    """Decode gzip JSON objects, rejecting arrays and scalars instead of treating them as logs."""
    text = gzip.decompress(body).decode("utf-8").strip()
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        records = [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        records = [json.loads(text)]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("every invocation record must be a JSON object")
    return records


def resolved_region(explicit: str | None, env: dict) -> str | None:
    """Return the region the AWS CLI would use: --region, AWS_REGION, then AWS_DEFAULT_REGION."""
    for value in (explicit, env.get("AWS_REGION"), env.get("AWS_DEFAULT_REGION")):
        if value and value.strip():
            return value.strip()
    return None


def logging_status_line(config: dict | None) -> str:
    """Return a one-line human summary of a GetModelInvocationLoggingConfiguration result."""
    if not config:
        return "logging is OFF"
    s3 = config.get("s3Config") or {}
    destination = s3.get("bucketName", "(no S3 destination)")
    cloudwatch = " + CloudWatch" if config.get("cloudWatchConfig") else ""
    return f"logging is ON -> s3://{destination}{cloudwatch}"
