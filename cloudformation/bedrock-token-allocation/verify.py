"""Prove one account's Bedrock logging works end to end and Vantage can read it.

Run this with credentials for the account you deployed the stack in (each
linked account, one at a time). It is read-only: checks the logging config
points at the expected bucket, finds recently delivered log objects,
validates a sample against what Vantage's reader accepts, and prints the
exact values to enter in the Vantage UI. Exits non-zero on the first failed
check, so it can gate automation. Requires: pip install boto3
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from bedrock import (
    day_prefixes,
    log_prefix,
    logging_status_line,
    object_key_pattern,
    record_problems,
    record_warnings,
    records_from_gz,
    resolved_region,
    vantage_connect_values,
)


# --- shell: AWS reads in, verdict out ----------------------------------------

def main() -> None:
    """Check config, delivery, and record shape for this account, then print the connect values."""
    args = parse_args()
    session = boto3.session.Session(region_name=resolved_region(args.region, os.environ))
    region = session.region_name
    if not region:
        sys.exit("no region. Model invocation logging is per-region, so this needs one:\n"
                 "  pass --region us-east-1, or set AWS_REGION or AWS_DEFAULT_REGION,\n"
                 "  or give the profile a default (aws configure set region us-east-1)")
    account_id = session.client("sts").get_caller_identity()["Account"]
    bucket = args.bucket or f"bedrock-mil-logs-{account_id}-{region}"
    print(f"Account {account_id}, region {region}, expecting bucket {bucket}\n")

    config = session.client("bedrock").get_model_invocation_logging_configuration() \
        .get("loggingConfig")
    check("logging configuration", logging_status_line(config),
          ok=bool(config) and (config.get("s3Config") or {}).get("bucketName") == bucket,
          hint=f"deploy bedrock-logging.yaml in {region}, or re-run with --region set to "
               "wherever you deployed. Logging is a per-region setting, so checking the "
               "wrong region looks exactly like a failed deploy")

    prefix = log_prefix(account_id, region, args.key_prefix)
    today = datetime.now(timezone.utc).date()
    keys = recent_object_keys(session, bucket, day_prefixes(prefix, today, args.days))
    check("log delivery", f"{len(keys)} object(s) in the last {args.days} day(s) "
                          f"under s3://{bucket}/{prefix}",
          ok=bool(keys),
          hint="logs appear a few minutes after the first model call once logging is on. "
               "Make one bedrock-runtime call (Converse or InvokeModel) and re-run, or "
               "widen the window with --days")

    pattern = object_key_pattern(account_id, region, args.key_prefix)
    record_keys = [key for key in keys if re.fullmatch(pattern, key)]
    check("key layout", f"{len(record_keys)}/{len(keys)} keys are invocation records "
                        "where Vantage reads",
          ok=bool(record_keys),
          hint=f"unexpected key example: {keys[0]}" if keys else "")
    if len(record_keys) < len(keys):
        print(f"  note: {len(keys) - len(record_keys)} other object(s) ignored. Bedrock "
              "writes bodies over 100 KB under a data/ subfolder, plus permission-check "
              "markers; neither is an invocation record")

    records, unreadable = sample_records(session, bucket, record_keys[:args.sample])
    problems = [(record.get("requestId", "?"), problem)
                for record in records for problem in record_problems(record)]
    check("record shape", f"{len(records)} record(s) sampled, {len(problems)} problem(s), "
                          f"{len(unreadable)} unreadable object(s)",
          ok=bool(records) and not problems and not unreadable,
          hint="; ".join([f"{key}: {error}" for key, error in unreadable[:2]]
                         + [f"{rid}: {problem}" for rid, problem in problems[:3]]))

    tagless = [warning for record in records for warning in record_warnings(record)]
    if tagless:
        print(f"  note: {len(tagless)}/{len(records)} sampled records carry no "
              "requestMetadata; see the README section on tagging")

    values = vantage_connect_values(bucket, account_id, region, args.key_prefix)
    print("\nAll checks passed. In Vantage (Settings -> AWS integration -> "
          "Model Invocation Logs -> Connect), select:")
    print(f"  bucket: {values['bucket']}")
    print(f"  prefix: {values['prefix']}   (auto-resolved by Vantage; shown for reference)")
    print(f"  region: {values['region']}")


def parse_args() -> argparse.Namespace:
    """Return the parsed CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bucket", default="",
                        help="log bucket name (default: bedrock-mil-logs-<account>-<region>)")
    parser.add_argument("--region", default=None,
                        help="region to verify (default: how the AWS CLI resolves it)")
    parser.add_argument("--key-prefix", default="",
                        help="KeyPrefix if you set one on the stack (default: none)")
    parser.add_argument("--days", type=int, default=2,
                        help="how many days back to look for delivered logs (default 2)")
    parser.add_argument("--sample", type=int, default=3,
                        help="how many objects to download and validate (default 3)")
    return parser.parse_args()


def check(name: str, detail: str, ok: bool, hint: str = "") -> None:
    """Print one check line and exit non-zero with the hint when it failed."""
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")
    if not ok:
        if hint:
            print(f"     {hint}")
        sys.exit(1)


def recent_object_keys(session: boto3.session.Session, bucket: str,
                       prefixes: list[str]) -> list[str]:
    """Return keys under the given day prefixes, newest last-modified first."""
    paginator = session.client("s3").get_paginator("list_objects_v2")
    entries = [entry
               for prefix in prefixes
               for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
               for entry in page.get("Contents", [])]
    entries.sort(key=lambda entry: entry["LastModified"], reverse=True)
    return [entry["Key"] for entry in entries]


def sample_records(session: boto3.session.Session, bucket: str,
                   keys: list[str]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Return (parsed records, [(key, error)] for objects that would not parse)."""
    client = session.client("s3")
    records: list[dict] = []
    unreadable: list[tuple[str, str]] = []
    for key in keys:
        try:
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            records += records_from_gz(body)
        except (OSError, EOFError, ValueError, ClientError) as error:
            unreadable.append((key, str(error)))
    return records, unreadable


if __name__ == "__main__":
    main()
