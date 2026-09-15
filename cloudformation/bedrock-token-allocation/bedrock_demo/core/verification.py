"""Pure checks for AWS log readiness, separate from Vantage ingestion evidence."""
from __future__ import annotations

from dataclasses import dataclass

from bedrock_demo.core.logs import record_problems, vantage_connect_values

DELIVERY_TYPES = ("text", "image", "embedding", "video", "audio")
PASSING = {"pass", "warning"}
PENDING_HINT = ("Pending: allow Bedrock delivery or S3 replication to finish, then rerun this "
                "command. For older logs, increase --days; objects created before replication "
                "was enabled need separate backfill.")
FAILED_HINT = ("AWS verification failed. Resolve the named configuration, identity, data, or "
               "permission error and rerun.")
VANTAGE_BOUNDARY = (
    "Vantage completion: UNVERIFIED by this AWS checker.",
    "In Settings -> Integrations -> AWS Bedrock, connect each original regional bucket. "
    "Complete Check Permissions, confirm successful Import History, and verify costs by the "
    "source AWS account and your exact requestMetadata tag keys.",
    "The central replica is your copy; it is not the native Vantage source.",
)


@dataclass(frozen=True)
class VerificationCheck:
    """One observable verification result, without log payloads or credentials."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class VerificationReport:
    """Source AWS evidence and the original-bucket handoff for native Vantage."""

    source_account_id: str
    bucket: str
    region: str
    key_prefix: str
    checks: tuple[VerificationCheck, ...]
    sample_keys: tuple[str, ...] = ()
    vantage_verified: bool = False

    @property
    def ok(self) -> bool:
        """Return whether every AWS check passed or only warned."""
        return bool(self.checks) and all(check.status in PASSING for check in self.checks)

    @property
    def connect_values(self) -> dict:
        """Return the original bucket values; replicas are never a native handoff."""
        if not self.source_account_id or not self.bucket or not self.region:
            return {}
        return vantage_connect_values(self.bucket, self.source_account_id, self.region,
                                      self.key_prefix)


def expected_request_tags(values: list[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE expectations without silently replacing conflicting values."""
    pairs = [value.partition("=") for value in values]
    if any(not separator or not key or not value for key, separator, value in pairs):
        raise ValueError("--expect-tag requires a nonempty KEY=VALUE")
    tags = {key: value for key, _, value in pairs}
    if any(tags[key] != value for key, _, value in pairs):
        raise ValueError("--expect-tag cannot specify different values for the same key")
    return tags


def verification_succeeded(report: VerificationReport,
                           replication: tuple[VerificationCheck, ...]) -> bool:
    """Return whether all requested AWS checks succeeded, without claiming Vantage completion."""
    return report.ok and all(check.status in PASSING for check in replication)


def verification_lines(report: VerificationReport,
                       replication: tuple[VerificationCheck, ...]) -> list[str]:
    """Render AWS results and an explicit boundary before the separate Vantage validation."""
    checks = (*report.checks, *replication)
    lines = [f"{check.status.upper():<7} {check.name}: {check.detail}" for check in checks]
    if any(check.status == "pending" for check in checks):
        lines.append(PENDING_HINT)
    if any(check.status == "fail" for check in checks):
        lines.append(FAILED_HINT)
    if report.source_account_id and report.bucket:
        values = report.connect_values
        lines.extend(["", "Original Vantage source (connect after AWS checks pass):",
                      f"  bucket: {values['bucket']}", f"  region: {values['region']}",
                      f"  scan prefix: {values['prefix']} "
                      "(auto-resolved by Vantage; shown for reference)"])
    lines.extend(["", *VANTAGE_BOUNDARY])
    return lines


def configuration_check(configuration: dict | None, bucket: str,
                        key_prefix: str) -> VerificationCheck:
    """Compare both the configured destination bucket and its exact optional prefix."""
    actual = (configuration or {}).get("s3Config") or {}
    expected = {"bucketName": bucket, "keyPrefix": key_prefix}
    configured = {"bucketName": actual.get("bucketName"), "keyPrefix": actual.get("keyPrefix", "")}
    status = "pass" if configured == expected else "fail"
    detail = f"Expected {expected!r}; observed {configured!r}."
    return VerificationCheck("logging configuration", status, detail)


def delivery_check(configuration: dict | None,
                   expected_delivery: str = "text") -> VerificationCheck:
    """Require current delivery for the requested modality even when older logs still exist."""
    if expected_delivery not in DELIVERY_TYPES:
        raise ValueError(f"Unsupported delivery type: {expected_delivery}")
    field = f"{expected_delivery}DataDeliveryEnabled"
    enabled = (configuration or {}).get(field) is True
    detail = (f"{field} is {'enabled' if enabled else 'disabled or unset'}; "
              "older logs do not prove current delivery.")
    return VerificationCheck("logging delivery mode", "pass" if enabled else "fail", detail)


def newest_object_keys(entries: list[dict]) -> tuple[str, ...]:
    """Return unique keys by newest modification time, then key for deterministic ties."""
    ordered = sorted(entries, key=lambda entry: (-entry["LastModified"].timestamp(), entry["Key"]))
    return tuple(dict.fromkeys(entry["Key"] for entry in ordered))


def record_checks(records: list[object], account_id: str, region: str,
                  expected_tags: dict[str, str] | None = None) -> tuple[VerificationCheck, ...]:
    """Validate sampled shape, origin identity, and optional expected request metadata."""
    if not records:
        return (VerificationCheck("sampled records", "fail",
                                  "No invocation records were decoded."),)
    invalid = [record for record in records if not isinstance(record, dict)]
    if invalid:
        return (VerificationCheck("sampled records", "fail",
                                  f"{len(invalid)} record(s) are not JSON objects."),)
    problems = [problem for record in records for problem in record_problems(record)]
    wrong_origin = [record for record in records
                    if record.get("accountId") != account_id or record.get("region") != region]
    checks = [
        VerificationCheck("record shape", "fail" if problems else "pass",
                          f"{len(records)} record(s); {len(problems)} shape problem(s). "
                          + "; ".join(problems[:3])),
        VerificationCheck("record origin", "fail" if wrong_origin else "pass",
                          f"{len(wrong_origin)} record(s) differ from account {account_id}, "
                          f"region {region}."),
    ]
    if expected_tags:
        matching = [record for record in records
                    if isinstance(record.get("requestMetadata"), dict)
                    and expected_tags.items() <= record["requestMetadata"].items()]
        checks.append(VerificationCheck("expected request metadata", "pass" if matching else "fail",
                                        f"{len(matching)} record(s) contain all expected tags."))
    else:
        tagless = sum(not record.get("requestMetadata") for record in records)
        checks.append(VerificationCheck("request metadata", "warning" if tagless else "pass",
                                        f"{tagless}/{len(records)} record(s) have no "
                                        "requestMetadata."))
    return tuple(checks)


def replication_status_check(key: str, status: str | None) -> VerificationCheck:
    """Distinguish unfinished replication from failed or ineligible source objects."""
    verdict = {"COMPLETE": "pass", "COMPLETED": "pass", "PENDING": "pending"}.get(status, "fail")
    return VerificationCheck("source replication", verdict,
                             f"{key}: {status or 'no replication status'}.")


def replica_checks(key: str, source: dict, destination: dict,
                   source_body: bytes, destination_body: bytes) -> tuple[VerificationCheck, ...]:
    """Require an actual S3 replica with identical bytes and object metadata."""
    metadata_fields = ("Metadata", "ContentType", "ContentEncoding", "ContentDisposition",
                       "CacheControl")
    metadata_equal = all(source.get(field) == destination.get(field) for field in metadata_fields)
    replica = destination.get("ReplicationStatus") == "REPLICA"
    return (
        VerificationCheck("destination replication", "pass" if replica else "fail",
                          f"{key}: {destination.get('ReplicationStatus', 'no replication status')}"
                          "."),
        VerificationCheck("replica bytes", "pass" if source_body == destination_body else "fail",
                          f"{key}: compared {len(source_body)} source bytes with "
                          f"{len(destination_body)} replica bytes."),
        VerificationCheck("replica metadata", "pass" if metadata_equal else "fail",
                          f"{key}: object metadata {'matches' if metadata_equal else 'differs'}."),
    )
