"""Verification tests with literal records and botocore's request/response stubs."""
from __future__ import annotations

import gzip
import io
import json
import unittest
from datetime import date, datetime, timezone

import boto3
from botocore.client import BaseClient
from botocore.stub import Stubber

from bedrock_demo.aws.verification import sampled_records, verify_replication, verify_source
from bedrock_demo.core.logs import record_problems, records_from_gz
from bedrock_demo.core.verification import (
    configuration_check,
    delivery_check,
    newest_object_keys,
    record_checks,
)


ACCOUNT = "123456789012"
REGION = "us-east-1"
BUCKET = f"bedrock-mil-logs-{ACCOUNT}-{REGION}"
CENTRAL = "central"
LOG_PREFIX = f"AWSLogs/{ACCOUNT}/BedrockModelInvocationLogs/{REGION}/"
KEY = f"{LOG_PREFIX}2026/09/14/12/request.json.gz"
IDENTITY = {"Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:user/test", "UserId": "test"}
RECORD = {
    "schemaType": "ModelInvocationLog", "timestamp": "2026-09-14T12:00:00Z",
    "accountId": ACCOUNT, "region": REGION, "requestId": "request-1",
    "operation": "Converse", "modelId": "amazon.nova-micro-v1:0",
    "input": {"inputTokenCount": 10}, "output": {"outputTokenCount": 5},
    "requestMetadata": {"team": "demo-alpha", "application": "bedrock-finops"},
}


def aws_client(service: str, region: str = REGION) -> BaseClient:
    """Build a client with dummy credentials so test setup never discovers real credentials."""
    return boto3.client(service, region_name=region, aws_access_key_id="test",
                        aws_secret_access_key="test")


class ClientSession:
    """Route requests to explicitly stubbed clients and retain their requested regions."""

    def __init__(self, clients: dict[str, BaseClient]) -> None:
        """Retain the clients owned by this test session."""
        self.clients = clients
        self.regions: list[tuple[str, str]] = []

    def client(self, service: str, *, region_name: str) -> BaseClient:
        """Return the stubbed service and record its endpoint region."""
        self.regions.append((service, region_name))
        return self.clients[service]


def object_response(body: bytes, status: str | None = None, metadata: dict | None = None) -> dict:
    """Return an S3 response with a fresh closable body stream."""
    response = {"Body": io.BytesIO(body), "Metadata": metadata or {},
                "ContentType": "application/json"}
    return response | ({"ReplicationStatus": status} if status else {})


def listing(*keys: str) -> dict:
    """Return one list_objects_v2 page whose entries were all modified on the fixture day."""
    modified = datetime(2026, 9, 14, tzinfo=timezone.utc)
    return {"Contents": [{"Key": key, "LastModified": modified} for key in keys]}


def source_clients() -> tuple[ClientSession, dict[str, BaseClient]]:
    """Return a session routing to fresh sts, bedrock, and s3 clients for one source check."""
    clients = {name: aws_client(name) for name in ("sts", "bedrock", "s3")}
    return ClientSession(clients), clients


def replication_checks(source: BaseClient, destination: BaseClient,
                       destination_region: str = REGION) -> tuple:
    """Run the replica comparison for the fixture key between two stubbed S3 clients."""
    return verify_replication(ClientSession({"s3": source}), ClientSession({"s3": destination}),
                              source_bucket=BUCKET, destination_bucket=CENTRAL, keys=[KEY],
                              source_region=REGION, destination_region=destination_region)


class VerificationTests(unittest.TestCase):
    """Exercise source identity, handoff accuracy, and replication evidence failures."""

    def test_configuration_compares_the_prefix_as_well_as_bucket(self) -> None:
        """A bucket match cannot hide a different configured key prefix."""
        config = {"s3Config": {"bucketName": BUCKET, "keyPrefix": "different/"}}
        self.assertEqual("fail", configuration_check(config, BUCKET, "").status)
        self.assertEqual("pass", configuration_check(config, BUCKET, "different/").status)

    def test_delivery_requires_the_requested_modality_to_be_enabled(self) -> None:
        """One enabled modality cannot hide a disabled or missing expected delivery flag."""
        config = {"textDataDeliveryEnabled": False, "imageDataDeliveryEnabled": True}
        self.assertEqual("fail", delivery_check(config).status)
        self.assertEqual("pass", delivery_check(config, "image").status)
        self.assertEqual("fail", delivery_check(config, "audio").status)
        with self.assertRaisesRegex(ValueError, "Unsupported delivery type"):
            delivery_check(config, "unknown")

    def test_record_origin_cannot_be_inferred_from_the_storage_path(self) -> None:
        """A valid-shaped record from another account or region must fail verification."""
        wrong_account = RECORD | {"accountId": "999999999999"}
        wrong_region = RECORD | {"region": "us-west-2"}
        checks = record_checks([RECORD, wrong_account, wrong_region], ACCOUNT, REGION)
        origin = next(check.status for check in checks if check.name == "record origin")
        self.assertEqual("fail", origin)
        self.assertEqual("fail", record_checks([[]], ACCOUNT, REGION)[0].status)

    def test_cross_region_inference_preserves_the_origin_region(self) -> None:
        """A different inferenceRegion must not invalidate logs written in the invoking region."""
        record = RECORD | {"modelId": "us.amazon.nova-micro-v1:0", "inferenceRegion": "us-west-2"}
        checks = record_checks([record], ACCOUNT, REGION)
        self.assertTrue(all(check.status == "pass" for check in checks))

    def test_json_arrays_and_scalars_are_not_native_log_records(self) -> None:
        """Malformed top-level values fail explicitly instead of crashing later lookups."""
        for value in ([], [RECORD], "text", 10, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                records_from_gz(gzip.compress(json.dumps(value).encode()))
        self.assertEqual(["record is not a JSON object"], record_problems([]))
        with self.assertRaises(ValueError):
            records_from_gz(gzip.compress((json.dumps(RECORD) + "\n[]\n").encode()))

    def test_expected_tags_require_a_matching_record(self) -> None:
        """Arbitrary request metadata does not prove the expected workload arrived."""
        missing = record_checks([RECORD], ACCOUNT, REGION, {"team": "demo-beta"})
        present = record_checks([RECORD], ACCOUNT, REGION, {"team": "demo-alpha"})
        self.assertEqual("fail", missing[-1].status)
        self.assertEqual("pass", present[-1].status)

    def test_recent_keys_are_sorted_and_deduplicated_across_pages(self) -> None:
        """Select newest samples rather than relying on S3's lexical listing order."""
        older = datetime(2026, 9, 13, tzinfo=timezone.utc)
        newer = datetime(2026, 9, 14, tzinfo=timezone.utc)
        entries = [{"Key": "older", "LastModified": older}, {"Key": "newer", "LastModified": newer},
                   {"Key": "newer", "LastModified": newer}]
        self.assertEqual(("newer", "older"), newest_object_keys(entries))

    def test_source_evidence_keeps_original_bucket_handoff_and_vantage_unverified(self) -> None:
        """Successful AWS reads prove delivery while leaving Vantage ingestion unverified."""
        session, clients = source_clients()
        body = gzip.compress(json.dumps(RECORD).encode())
        with Stubber(clients["sts"]) as identity, Stubber(clients["bedrock"]) as logging, \
                Stubber(clients["s3"]) as storage:
            identity.add_response("get_caller_identity", IDENTITY, {})
            logging.add_response("get_model_invocation_logging_configuration", {
                "loggingConfig": {"s3Config": {"bucketName": BUCKET},
                                  "textDataDeliveryEnabled": True}}, {})
            storage.add_response("list_objects_v2", listing(KEY),
                                 {"Bucket": BUCKET, "Prefix": f"{LOG_PREFIX}2026/09/14/"})
            storage.add_response("get_object", object_response(body),
                                 {"Bucket": BUCKET, "Key": KEY})
            report = verify_source(session, region=REGION, today=date(2026, 9, 14), days=1)
            storage.assert_no_pending_responses()
        self.assertTrue(report.ok)
        self.assertFalse(report.vantage_verified)
        self.assertEqual(BUCKET, report.connect_values["bucket"])
        self.assertEqual((KEY,), report.sample_keys)

    def test_older_valid_logs_cannot_mask_disabled_text_delivery(self) -> None:
        """Fail current text readiness even when a retained tagged invocation is readable."""
        session, clients = source_clients()
        body = gzip.compress(json.dumps(RECORD).encode())
        with Stubber(clients["sts"]) as identity, Stubber(clients["bedrock"]) as logging, \
                Stubber(clients["s3"]) as storage:
            identity.add_response("get_caller_identity", IDENTITY, {})
            logging.add_response("get_model_invocation_logging_configuration", {
                "loggingConfig": {"s3Config": {"bucketName": BUCKET},
                                  "textDataDeliveryEnabled": False,
                                  "imageDataDeliveryEnabled": True}}, {})
            storage.add_response("list_objects_v2", {"Contents": []},
                                 {"Bucket": BUCKET, "Prefix": f"{LOG_PREFIX}2026/09/15/"})
            storage.add_response("list_objects_v2", listing(KEY),
                                 {"Bucket": BUCKET, "Prefix": f"{LOG_PREFIX}2026/09/14/"})
            storage.add_response("get_object", object_response(body),
                                 {"Bucket": BUCKET, "Key": KEY})
            report = verify_source(session, region=REGION, today=date(2026, 9, 15), days=2,
                                   expected_tags={"team": "demo-alpha"})
            identity.assert_no_pending_responses()
            logging.assert_no_pending_responses()
            storage.assert_no_pending_responses()
        checks = {check.name: check for check in report.checks}
        self.assertFalse(report.ok)
        self.assertEqual("fail", checks["logging delivery mode"].status)
        self.assertEqual("pass", checks["log delivery"].status)
        self.assertEqual("pass", checks["expected request metadata"].status)
        self.assertFalse(report.vantage_verified)

    def test_source_permission_failure_returns_a_failed_report(self) -> None:
        """AWS authentication errors remain failures rather than misleading empty-log results."""
        sts = aws_client("sts")
        with Stubber(sts) as identity:
            identity.add_client_error("get_caller_identity", service_error_code="AccessDenied",
                                      http_status_code=403)
            report = verify_source(ClientSession({"sts": sts}), region=REGION,
                                   today=date(2026, 9, 14))
        self.assertFalse(report.ok)
        self.assertEqual("AWS access", report.checks[0].name)
        self.assertEqual({}, report.connect_values)

    def test_corrupt_sample_reports_a_failure_without_returning_payload(self) -> None:
        """Bad gzip data becomes an actionable check result rather than ending verification."""
        s3 = aws_client("s3")
        with Stubber(s3) as storage:
            storage.add_response("get_object", object_response(b"not-gzip-payload"),
                                 {"Bucket": BUCKET, "Key": KEY})
            records, checks = sampled_records(s3, BUCKET, KEY)
        self.assertEqual([], records)
        self.assertEqual("fail", checks[0].status)
        self.assertNotIn("not-gzip-payload", checks[0].detail)

    def test_replication_requires_s3_status_and_a_separate_destination_client(self) -> None:
        """Separate destination credentials and region must observe a byte-identical replica."""
        source, destination = aws_client("s3"), aws_client("s3", "us-west-2")
        source_session = ClientSession({"s3": source})
        destination_session = ClientSession({"s3": destination})
        with Stubber(source) as original, Stubber(destination) as replica:
            original.add_response("get_object",
                                  object_response(b"same", "COMPLETED", {"origin": "preserved"}),
                                  {"Bucket": BUCKET, "Key": KEY})
            replica.add_response("get_object",
                                 object_response(b"same", "REPLICA", {"origin": "preserved"}),
                                 {"Bucket": CENTRAL, "Key": KEY})
            checks = verify_replication(source_session, destination_session, source_bucket=BUCKET,
                                        destination_bucket=CENTRAL, keys=[KEY],
                                        source_region=REGION, destination_region="us-west-2")
            original.assert_no_pending_responses()
            replica.assert_no_pending_responses()
        self.assertTrue(all(check.status == "pass" for check in checks))
        self.assertEqual([("s3", "us-west-2")], destination_session.regions)

    def test_pending_replication_is_not_reported_as_complete(self) -> None:
        """A pending source returns pending without pretending a central object exists."""
        source, destination = aws_client("s3"), aws_client("s3")
        with Stubber(source) as original, Stubber(destination):
            original.add_response("get_object", object_response(b"same", "PENDING"),
                                  {"Bucket": BUCKET, "Key": KEY})
            checks = replication_checks(source, destination)
        self.assertEqual(["pending"], [check.status for check in checks])

    def test_manual_or_modified_copy_fails_replication_evidence(self) -> None:
        """A same-key object alone does not prove replication or payload preservation."""
        source, destination = aws_client("s3"), aws_client("s3")
        with Stubber(source) as original, Stubber(destination) as replica:
            original.add_response("get_object",
                                  object_response(b"original", "COMPLETED", {"origin": "original"}),
                                  {"Bucket": BUCKET, "Key": KEY})
            replica.add_response("get_object",
                                 object_response(b"changed", metadata={"origin": "changed"}),
                                 {"Bucket": CENTRAL, "Key": KEY})
            checks = replication_checks(source, destination)
        self.assertEqual(["pass", "fail", "fail", "fail"], [check.status for check in checks])

    def test_destination_permission_failure_is_not_a_successful_replication_check(self) -> None:
        """A completed source status cannot substitute for reading the destination replica."""
        source, destination = aws_client("s3"), aws_client("s3")
        with Stubber(source) as original, Stubber(destination) as replica:
            original.add_response("get_object", object_response(b"original", "COMPLETED"),
                                  {"Bucket": BUCKET, "Key": KEY})
            replica.add_client_error("get_object", service_error_code="AccessDenied",
                                     http_status_code=403,
                                     expected_params={"Bucket": CENTRAL, "Key": KEY})
            checks = replication_checks(source, destination)
        self.assertEqual(["fail"], [check.status for check in checks])
        self.assertIn("AccessDenied", checks[0].detail)


if __name__ == "__main__":
    unittest.main()
