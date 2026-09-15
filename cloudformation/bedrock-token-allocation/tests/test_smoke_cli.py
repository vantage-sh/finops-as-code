"""Exercise one-call smoke intent and failure recovery without making AWS requests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ReadTimeoutError

from bedrock_demo.cli.smoke import main


ACCOUNT = "123456789012"
REGION = "us-east-1"
MODEL = "us.amazon.nova-micro-v1:0"
SESSION = "bedrock_demo.cli.smoke.boto3.session.Session"
IDENTITY = {"Account": ACCOUNT}
RESPONSE = {"ResponseMetadata": {"RequestId": "smoke-request"},
            "usage": {"inputTokens": 8, "outputTokens": 1, "totalTokens": 9},
            "output": {"message": {"content": [{"text": "hello"}]}}}


class SmokeCliTests(unittest.TestCase):
    """Keep billed calls bounded and protect their evidence against repeated submission."""

    def setUp(self) -> None:
        """Create an isolated receipt path and inert AWS clients for each command."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "smoke.json"
        self.args = ["--account-id", ACCOUNT, "--region", REGION, "--model-id", MODEL,
                     "--tag", "team=demo", "--output", str(self.output)]
        self.identity = Mock()
        self.identity.get_caller_identity.return_value = IDENTITY
        self.runtime = Mock()
        self.runtime.converse.return_value = RESPONSE
        clients = {"sts": self.identity, "bedrock-runtime": self.runtime}
        self.session = Mock()
        self.session.client.side_effect = lambda service, **kwargs: clients[service]

    def run_main(self) -> int:
        """Run the command against the stubbed session with its output captured."""
        with patch(SESSION, return_value=self.session), redirect_stdout(io.StringIO()):
            return main(self.args)

    def test_success_saves_intent_before_one_bounded_call(self) -> None:
        """Disable API retries and preserve request identity without saving generated content."""
        intents: list[dict] = []

        def invoke(**request: object) -> dict:
            """Observe that the complete correlation intent exists before a billed request."""
            intents.append(json.loads(self.output.read_text()))
            return RESPONSE

        self.runtime.converse.side_effect = invoke
        status = self.run_main()
        self.assertEqual(0, status)
        self.runtime.converse.assert_called_once()
        request = self.runtime.converse.call_args.kwargs
        self.assertEqual({"maxTokens": 16, "temperature": 0}, request["inferenceConfig"])
        self.assertEqual({"team": "demo"}, request["requestMetadata"])
        self.assertEqual({"total_max_attempts": 1},
                         self.session.client.call_args.kwargs["config"].retries)
        self.assertEqual(ACCOUNT, intents[0]["expected_account_id"])
        self.assertEqual(ACCOUNT, intents[0]["account_id"])
        self.assertEqual(MODEL, intents[0]["model_id"])
        self.assertEqual(REGION, intents[0]["region"])
        self.assertEqual({"team": "demo"}, intents[0]["request_metadata"])
        self.assertEqual("submitted", intents[0]["status"])
        self.assertFalse(intents[0]["vantage_verified"])
        receipt = json.loads(self.output.read_text())
        self.assertEqual("smoke-request", receipt["request_id"])
        self.assertEqual(RESPONSE["usage"], receipt["usage"])
        self.assertNotIn("output", receipt)
        self.assertNotIn("messages", receipt)

    def test_existing_receipt_prevents_all_aws_calls(self) -> None:
        """A rerun leaves earlier evidence intact before even resolving an AWS session."""
        self.output.write_text("previous receipt")
        with patch(SESSION) as session, redirect_stdout(io.StringIO()):
            status = main(self.args)
        self.assertEqual(1, status)
        session.assert_not_called()
        self.assertEqual("previous receipt", self.output.read_text())

    def test_another_run_claiming_the_receipt_prevents_the_billed_call(self) -> None:
        """Exclusive creation closes the race between the existence check and submission."""
        def concurrent_claim() -> dict:
            """Simulate another command claiming the path after the initial existence check."""
            self.output.write_text("another run's intent")
            return IDENTITY

        self.identity.get_caller_identity.side_effect = concurrent_claim
        with patch(SESSION, return_value=self.session), redirect_stdout(io.StringIO()) as output:
            status = main(self.args)
        self.assertEqual(1, status)
        self.runtime.converse.assert_not_called()
        self.assertEqual("another run's intent", self.output.read_text())
        self.assertIn("receipt already exists", output.getvalue())
        self.assertEqual(["sts"], [call.args[0] for call in self.session.client.call_args_list])

    def test_wrong_account_does_not_claim_receipt_or_invoke(self) -> None:
        """A mismatched AWS profile cannot spend money or block a later correct invocation."""
        self.identity.get_caller_identity.return_value = {"Account": "999999999999"}
        status = self.run_main()
        self.assertEqual(1, status)
        self.runtime.converse.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_uncertain_response_preserves_intent_and_blocks_a_second_call(self) -> None:
        """A network timeout keeps correlation evidence and cannot trigger an automatic repeat."""
        self.runtime.converse.side_effect = ReadTimeoutError(endpoint_url="https://example.invalid")
        with patch(SESSION, return_value=self.session) as session, redirect_stdout(io.StringIO()):
            first = main(self.args)
            saved = self.output.read_text()
            second = main(self.args)
        self.assertEqual((1, 1), (first, second))
        self.runtime.converse.assert_called_once()
        session.assert_called_once()
        self.assertEqual(saved, self.output.read_text())
        intent = json.loads(saved)
        self.assertEqual("submitted", intent["status"])
        self.assertEqual(MODEL, intent["model_id"])
        self.assertEqual(ACCOUNT, intent["expected_account_id"])
        self.assertEqual({"team": "demo"}, intent["request_metadata"])


if __name__ == "__main__":
    unittest.main()
