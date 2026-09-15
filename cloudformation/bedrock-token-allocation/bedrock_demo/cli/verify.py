"""Check AWS log delivery and optional replication; Vantage completion is a separate check."""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError

from bedrock_demo.aws.verification import verify_replication, verify_source
from bedrock_demo.core.logs import resolved_region
from bedrock_demo.core.verification import (
    DELIVERY_TYPES,
    VerificationCheck,
    VerificationReport,
    expected_request_tags,
    verification_lines,
    verification_succeeded,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse source, destination, sampling, and evidence-output arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket",
                        help="original log bucket; defaults to bedrock-mil-logs-<account>-<region>")
    parser.add_argument("--region",
                        help="original account's logging region; defaults to the AWS CLI chain")
    parser.add_argument("--key-prefix", default="",
                        help="exact KeyPrefix configured on the original stack")
    parser.add_argument("--days", type=int, default=2,
                        help="recent source log days to scan (default: 2)")
    parser.add_argument("--sample", type=int, default=3,
                        help="newest invocation objects to read (default: 3)")
    parser.add_argument("--delivery-type", choices=DELIVERY_TYPES, default="text",
                        help="require this logging modality to be enabled now (default: text)")
    parser.add_argument("--destination-bucket",
                        help="optional central replication bucket to verify")
    parser.add_argument("--destination-region",
                        help="central bucket's actual region; required with --destination-bucket")
    parser.add_argument("--destination-profile",
                        help="AWS profile for reading the central bucket; "
                             "defaults to current credentials")
    parser.add_argument("--expect-tag", action="append", default=[], metavar="KEY=VALUE",
                        help="require a sampled invocation with these requestMetadata tags; "
                             "repeat for several keys")
    parser.add_argument("--json-output", type=Path,
                        help="save structured AWS evidence without raw log bodies")
    args = parser.parse_args(argv)
    if args.days < 1 or args.sample < 1:
        parser.error("--days and --sample must be positive")
    if args.destination_bucket and not args.destination_region:
        parser.error("--destination-bucket requires --destination-region")
    if (args.destination_region or args.destination_profile) and not args.destination_bucket:
        parser.error("--destination-region and --destination-profile require --destination-bucket")
    try:
        args.expected_tags = expected_request_tags(args.expect_tag)
    except ValueError as error:
        parser.error(str(error))
    return args


def evidence_payload(args: argparse.Namespace, checked_at: datetime, source: VerificationReport,
                     replication: tuple[VerificationCheck, ...]) -> dict:
    """Return the saved AWS evidence, always leaving Vantage completion unverified."""
    return {"schema_version": 1, "checked_at": checked_at.isoformat(), "source": asdict(source),
            "expected_delivery": args.delivery_type, "connect_values": source.connect_values,
            "replication_requested": bool(args.destination_bucket),
            "destination_bucket": args.destination_bucket,
            "destination_region": args.destination_region,
            "replication_checks": [asdict(check) for check in replication],
            "aws_checks_passed": verification_succeeded(source, replication),
            "vantage_verified": False}


def main(argv: list[str] | None = None) -> int:
    """Read AWS evidence, print the original-source handoff, and optionally save the report."""
    args = parse_args(argv)
    checked_at = datetime.now(timezone.utc)
    try:
        session = boto3.session.Session(region_name=resolved_region(args.region, os.environ))
    except BotoCoreError as error:
        print(f"FAIL AWS session: {error}")
        return 1
    if not session.region_name:
        print("FAIL no source region: use --region, AWS_REGION, AWS_DEFAULT_REGION, "
              "or a profile default.")
        return 2
    source = verify_source(session, region=session.region_name, today=checked_at.date(),
                           bucket=args.bucket, key_prefix=args.key_prefix, days=args.days,
                           sample=args.sample, expected_tags=args.expected_tags,
                           expected_delivery=args.delivery_type)
    replication: tuple[VerificationCheck, ...] = ()
    if args.destination_bucket:
        try:
            destination = boto3.session.Session(profile_name=args.destination_profile,
                                                region_name=args.destination_region)
            replication = verify_replication(session, destination, source_bucket=source.bucket,
                                             destination_bucket=args.destination_bucket,
                                             keys=source.sample_keys, source_region=source.region,
                                             destination_region=args.destination_region)
        except BotoCoreError as error:
            replication = (VerificationCheck("destination session", "fail", str(error)),)
    print("\n".join(verification_lines(source, replication)))
    if args.json_output:
        payload = evidence_payload(args, checked_at, source, replication)
        try:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError as error:
            print(f"FAIL evidence output: {error}")
            return 1
        print(f"\nAWS evidence saved to {args.json_output}")
    return 0 if verification_succeeded(source, replication) else 1


if __name__ == "__main__":
    raise SystemExit(main())
