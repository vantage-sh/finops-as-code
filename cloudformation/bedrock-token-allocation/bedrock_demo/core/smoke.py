"""Bounded native test invocation and evidence without application content."""
from __future__ import annotations


def smoke_request(model_id: str, tags: dict[str, str]) -> dict:
    """Return one short Converse request carrying the exact attribution tags."""
    if not model_id or not tags or len(tags) > 16:
        raise ValueError("Provide a model ID and between 1 and 16 request tags")
    if any(not key or not value or len(key) > 256 or len(value) > 256
           for key, value in tags.items()):
        raise ValueError("Request tag keys and values must contain 1-256 characters")
    return {"modelId": model_id,
            "messages": [{"role": "user", "content": [{"text": "Reply with the word hello."}]}],
            "inferenceConfig": {"maxTokens": 16, "temperature": 0}, "requestMetadata": dict(tags)}


def invocation_receipt(account_id: str, region: str, request: dict, response: dict,
                       called_at: str) -> dict:
    """Return request identity and usage to correlate with delivered logs and billed tags."""
    return {"account_id": account_id, "region": region, "called_at": called_at,
            "model_id": request["modelId"], "request_metadata": dict(request["requestMetadata"]),
            "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
            "usage": dict(response.get("usage", {})), "vantage_verified": False}
