"""CLI checks for argument validation, distinct AWS sessions, and truthful saved evidence."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bedrock_demo.cli.verify import main, parse_args
from bedrock_demo.core.verification import VerificationCheck, VerificationReport

SESSION = "bedrock_demo.cli.verify.boto3.session.Session"
SOURCE = "bedrock_demo.cli.verify.verify_source"
REPLICATION = "bedrock_demo.cli.verify.verify_replication"
PASSING_ORIGIN = (VerificationCheck("record origin", "pass", "expected account"),)


class VerifyCliTests(unittest.TestCase):
    """Keep AWS evidence, replica status, and actual Vantage completion distinct."""

    def assert_rejected(self, argv: list[str]) -> None:
        """Require argparse to exit with its usage status for the given arguments."""
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            parse_args(argv)
        self.assertEqual(2, error.exception.code)

    def test_destination_requires_explicit_bucket_and_region(self) -> None:
        """A destination profile or bucket cannot quietly reuse the source endpoint."""
        self.assert_rejected(["--destination-bucket", "central"])
        self.assert_rejected(["--destination-profile", "central-reader"])

    def test_expect_tags_parse_exact_keys_and_reject_conflicting_values(self) -> None:
        """Tag expectations keep values containing equals and reject ambiguous repeated keys."""
        args = parse_args(["--expect-tag", "team=alpha",
                           "--expect-tag", "application=demo=bedrock"])
        self.assertEqual({"team": "alpha", "application": "demo=bedrock"}, args.expected_tags)
        self.assert_rejected(["--expect-tag", "team=alpha", "--expect-tag", "team=beta"])
        self.assert_rejected(["--sample", "0"])

    def test_delivery_type_defaults_to_text_and_rejects_unknown_modes(self) -> None:
        """Require a supported current delivery flag without guessing a modality from old logs."""
        self.assertEqual("text", parse_args([]).delivery_type)
        self.assertEqual("embedding", parse_args(["--delivery-type", "embedding"]).delivery_type)
        self.assert_rejected(["--delivery-type", "unknown"])

    def test_pending_replica_exits_nonzero_and_saves_unverified_vantage_evidence(self) -> None:
        """A successful original plus pending replication must not emit a completed result."""
        source_session = SimpleNamespace(region_name="us-east-1")
        destination_session = SimpleNamespace(region_name="us-west-2")
        source_report = VerificationReport("123456789012", "original", "us-east-1", "",
                                           PASSING_ORIGIN, ("original-key",))
        pending = (VerificationCheck("source replication", "pending", "PENDING"),)
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "evidence.json"
            with patch(SESSION, side_effect=[source_session, destination_session]) as sessions, \
                    patch(SOURCE, return_value=source_report) as source, \
                    patch(REPLICATION, return_value=pending) as replication, \
                    redirect_stdout(io.StringIO()) as output:
                status = main(["--region", "us-east-1", "--destination-bucket", "central",
                               "--destination-region", "us-west-2",
                               "--destination-profile", "central-reader",
                               "--delivery-type", "image", "--expect-tag", "team=alpha",
                               "--json-output", str(output_path)])
            payload = json.loads(output_path.read_text())
        self.assertEqual(1, status)
        self.assertEqual({"profile_name": "central-reader", "region_name": "us-west-2"},
                         sessions.call_args_list[1].kwargs)
        self.assertEqual({"team": "alpha"}, source.call_args.kwargs["expected_tags"])
        self.assertEqual("image", source.call_args.kwargs["expected_delivery"])
        self.assertEqual("image", payload["expected_delivery"])
        self.assertEqual((source_session, destination_session), replication.call_args.args)
        self.assertEqual("original", payload["connect_values"]["bucket"])
        self.assertFalse(payload["aws_checks_passed"])
        self.assertFalse(payload["vantage_verified"])
        self.assertIn("rerun this command", output.getvalue())
        self.assertIn("Vantage completion: UNVERIFIED", output.getvalue())

    def test_source_only_check_never_creates_a_destination_connection(self) -> None:
        """Replication remains opt-in and a passing AWS result still declares Vantage unverified."""
        source_report = VerificationReport("123456789012", "original", "us-east-1", "",
                                           PASSING_ORIGIN)
        with patch(SESSION, return_value=SimpleNamespace(region_name="us-east-1")) as session, \
                patch(SOURCE, return_value=source_report), \
                patch(REPLICATION) as replication, redirect_stdout(io.StringIO()) as output:
            status = main(["--region", "us-east-1"])
        self.assertEqual(0, status)
        session.assert_called_once()
        replication.assert_not_called()
        self.assertIn("bucket: original", output.getvalue())
        self.assertIn("Vantage completion: UNVERIFIED", output.getvalue())


if __name__ == "__main__":
    unittest.main()
