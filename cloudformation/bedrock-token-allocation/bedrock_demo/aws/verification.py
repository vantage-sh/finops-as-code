"""Read AWS evidence without claiming that Vantage has ingested or allocated it."""
from __future__ import annotations

import re
import zlib
from contextlib import closing
from datetime import date
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from bedrock_demo.core.logs import day_prefixes, log_prefix, object_key_pattern, records_from_gz
from bedrock_demo.core.verification import (
    VerificationCheck,
    VerificationReport,
    configuration_check,
    delivery_check,
    newest_object_keys,
    record_checks,
    replica_checks,
    replication_status_check,
)

if TYPE_CHECKING:
    from boto3.session import Session
    from botocore.client import BaseClient

DECODE_ERRORS = (OSError, EOFError, ValueError, UnicodeError, zlib.error)


def read_object(client: BaseClient, bucket: str, key: str) -> tuple[dict, bytes]:
    """Read one object version's metadata and body together and close its stream."""
    response = client.get_object(Bucket=bucket, Key=key)
    with closing(response["Body"]) as body:
        contents = body.read()
    return {key: value for key, value in response.items() if key != "Body"}, contents


def recent_keys(client: BaseClient, bucket: str, prefixes: list[str]) -> tuple[str, ...]:
    """List all requested day pages and return keys in deterministic newest-first order."""
    paginator = client.get_paginator("list_objects_v2")
    entries = [entry for prefix in prefixes
               for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
               for entry in page.get("Contents", [])]
    return newest_object_keys(entries)


def sampled_records(client: BaseClient, bucket: str,
                    key: str) -> tuple[list[object], tuple[VerificationCheck, ...]]:
    """Decode one sample, reporting read and decoding errors without leaking its payload."""
    try:
        _, body = read_object(client, bucket, key)
        return records_from_gz(body), ()
    except (BotoCoreError, ClientError) as error:
        return [], (VerificationCheck("sample access", "fail", f"{key}: {error}"),)
    except DECODE_ERRORS:
        return [], (VerificationCheck("sample decoding", "fail", f"{key}: invalid gzip or JSON."),)


def verify_source(session: Session, *, region: str, today: date, bucket: str | None = None,
                  key_prefix: str = "", days: int = 2, sample: int = 3,
                  expected_tags: dict[str, str] | None = None,
                  expected_delivery: str = "text") -> VerificationReport:
    """Check original-account AWS delivery and return evidence for a separate Vantage check."""
    if days < 1 or sample < 1:
        raise ValueError("days and sample must be positive")
    checks: list[VerificationCheck] = []
    account_id = ""
    sample_keys: tuple[str, ...] = ()
    try:
        account_id = session.client("sts", region_name=region).get_caller_identity()["Account"]
        bucket = bucket or f"bedrock-mil-logs-{account_id}-{region}"
        bedrock = session.client("bedrock", region_name=region)
        config = bedrock.get_model_invocation_logging_configuration().get("loggingConfig")
        checks.append(configuration_check(config, bucket, key_prefix))
        if checks[-1].status != "pass":
            return VerificationReport(account_id, bucket, region, key_prefix, tuple(checks))
        checks.append(delivery_check(config, expected_delivery))
        client = session.client("s3", region_name=region)
        prefix = log_prefix(account_id, region, key_prefix)
        keys = recent_keys(client, bucket, day_prefixes(prefix, today, days))
        pattern = object_key_pattern(account_id, region, key_prefix)
        sample_keys = tuple(key for key in keys if re.fullmatch(pattern, key))[:sample]
        checks.append(VerificationCheck("log delivery", "pass" if sample_keys else "pending",
                                        f"{len(sample_keys)} invocation object(s) selected from "
                                        f"{len(keys)} recent object(s)."))
        if sample_keys:
            samples = [sampled_records(client, bucket, key) for key in sample_keys]
            checks.extend(check for _, errors in samples for check in errors)
            records = [record for rows, _ in samples for record in rows]
            checks.extend(record_checks(records, account_id, region, expected_tags))
    except (BotoCoreError, ClientError) as error:
        checks.append(VerificationCheck("AWS access", "fail", str(error)))
    return VerificationReport(account_id, bucket or "", region, key_prefix, tuple(checks),
                              sample_keys)


def verify_replica_object(source_client: BaseClient, destination_client: BaseClient, *,
                          source_bucket: str, destination_bucket: str,
                          key: str) -> tuple[VerificationCheck, ...]:
    """Verify one unchanged key replicated, using separate source and destination clients."""
    try:
        source, source_body = read_object(source_client, source_bucket, key)
        status = replication_status_check(key, source.get("ReplicationStatus"))
        if status.status != "pass":
            return (status,)
        destination, destination_body = read_object(destination_client, destination_bucket, key)
        return (status, *replica_checks(key, source, destination, source_body, destination_body))
    except (BotoCoreError, ClientError) as error:
        return (VerificationCheck("replica access", "fail", f"{key}: {error}"),)


def verify_replication(source_session: Session, destination_session: Session, *,
                       source_bucket: str, destination_bucket: str,
                       keys: tuple[str, ...] | list[str], source_region: str,
                       destination_region: str) -> tuple[VerificationCheck, ...]:
    """Compare sampled originals with actual central replicas, independently of Vantage."""
    if not keys:
        return (VerificationCheck("replication samples", "pending",
                                  "No original invocation keys are available yet."),)
    try:
        source_client = source_session.client("s3", region_name=source_region)
        destination_client = destination_session.client("s3", region_name=destination_region)
        return tuple(check for key in dict.fromkeys(keys)
                     for check in verify_replica_object(source_client, destination_client,
                                                        source_bucket=source_bucket,
                                                        destination_bucket=destination_bucket,
                                                        key=key))
    except (BotoCoreError, ClientError) as error:
        return (VerificationCheck("replica access", "fail", str(error)),)
