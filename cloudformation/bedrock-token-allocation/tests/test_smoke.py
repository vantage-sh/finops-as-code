"""Pure tests for bounded Bedrock smoke requests and content-free receipts."""
from __future__ import annotations

import copy
import inspect
import unittest

from bedrock_demo.core.smoke import invocation_receipt, smoke_request

PROMPT = [{"role": "user", "content": [{"text": "Reply with the word hello."}]}]


class SmokeRequestTests(unittest.TestCase):
    """Keep test traffic small and preserve customer attribution metadata exactly."""

    def test_fixed_short_prompt_and_token_cap(self) -> None:
        """Callers choose model and tags while the prompt and output cap remain fixed."""
        request = smoke_request("amazon.nova-micro-v1:0", {"team": "test"})
        self.assertEqual(list(inspect.signature(smoke_request).parameters), ["model_id", "tags"])
        self.assertEqual(request["messages"], PROMPT)
        self.assertEqual(request["inferenceConfig"], {"maxTokens": 16, "temperature": 0})

    def test_model_and_metadata_are_preserved_without_mutation(self) -> None:
        """The request carries exact model and tag values in an independent dictionary."""
        model = "us.amazon.nova-micro-v1:0"
        tags = {"team": "growth", "application": "checkout", "environment": "test"}
        before = copy.deepcopy(tags)
        request = smoke_request(model, tags)
        self.assertEqual(request["modelId"], model)
        self.assertEqual(request["requestMetadata"], tags)
        self.assertIsNot(request["requestMetadata"], tags)
        self.assertEqual(tags, before)

    def test_accepts_one_and_sixteen_tags(self) -> None:
        """Both supported tag-count boundaries yield a bounded request."""
        for count in (1, 16):
            with self.subTest(count=count):
                tags = {f"tag-{number}": "value" for number in range(count)}
                self.assertEqual(smoke_request("model", tags)["requestMetadata"], tags)

    def test_rejects_zero_and_seventeen_tags(self) -> None:
        """Missing attribution or too many tags fails before any model invocation."""
        for tags in ({}, {f"tag-{number}": "value" for number in range(17)}):
            with self.subTest(count=len(tags)), self.assertRaises(ValueError):
                smoke_request("model", tags)

    def test_accepts_one_and_256_character_keys_and_values(self) -> None:
        """Key and value lengths at their documented boundaries remain unchanged."""
        for length in (1, 256):
            with self.subTest(length=length):
                tags = {"k" * length: "v" * length}
                self.assertEqual(smoke_request("model", tags)["requestMetadata"], tags)

    def test_rejects_empty_and_oversized_keys_or_values(self) -> None:
        """Each invalid tag dimension is rejected independently."""
        invalid = ({"": "value"}, {"key": ""}, {"k" * 257: "value"}, {"key": "v" * 257})
        for tags in invalid:
            with self.subTest(tags=tags), self.assertRaisesRegex(ValueError, "1-256"):
                smoke_request("model", tags)

    def test_rejects_an_empty_model(self) -> None:
        """A missing model is caught before a paid API call can be attempted."""
        with self.assertRaises(ValueError):
            smoke_request("", {"team": "test"})


class InvocationReceiptTests(unittest.TestCase):
    """Persist correlation and token evidence without recording model content."""

    def test_receipt_keeps_identity_usage_and_metadata_without_model_content(self) -> None:
        """Only the declared correlation fields cross into a durable receipt."""
        request = smoke_request("amazon.nova-micro-v1:0",
                                {"team": "test", "environment": "sandbox"})
        response = {
            "ResponseMetadata": {"RequestId": "request-123",
                                 "HTTPHeaders": {"x-sensitive": "omit-me"}},
            "usage": {"inputTokens": 8, "outputTokens": 2, "totalTokens": 10},
            "output": {"message": {"content": [{"text": "private model output"}]}},
            "stopReason": "end_turn",
        }
        original_request, original_response = copy.deepcopy(request), copy.deepcopy(response)
        receipt = invocation_receipt("111122223333", "us-west-2", request, response,
                                     "2026-09-14T20:00:00Z")
        self.assertEqual(receipt, {
            "account_id": "111122223333", "region": "us-west-2",
            "called_at": "2026-09-14T20:00:00Z", "model_id": "amazon.nova-micro-v1:0",
            "request_metadata": {"team": "test", "environment": "sandbox"},
            "request_id": "request-123",
            "usage": {"inputTokens": 8, "outputTokens": 2, "totalTokens": 10},
            "vantage_verified": False,
        })
        self.assertEqual(request, original_request)
        self.assertEqual(response, original_response)
        self.assertIsNot(receipt["request_metadata"], request["requestMetadata"])
        self.assertIsNot(receipt["usage"], response["usage"])

    def test_missing_response_identity_or_usage_is_not_invented(self) -> None:
        """An incomplete response stays incomplete and never claims Vantage verification."""
        request = smoke_request("model", {"team": "test"})
        receipt = invocation_receipt("111122223333", "us-east-1", request, {}, "now")
        self.assertIsNone(receipt["request_id"])
        self.assertEqual(receipt["usage"], {})
        self.assertFalse(receipt["vantage_verified"])


if __name__ == "__main__":
    unittest.main()
