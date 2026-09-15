"""Make one explicitly requested, short billed Bedrock call and save its identity."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from bedrock_demo.core.smoke import invocation_receipt, smoke_request
from bedrock_demo.core.verification import expected_request_tags

RECEIPT_EXISTS = ("receipt already exists; inspect it rather than repeating a potentially "
                  "billed request")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the account guard, target model, attribution tags, and receipt path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True,
                        help="expected account; refuse another active AWS profile")
    parser.add_argument("--region", required=True)
    parser.add_argument("--model-id", required=True,
                        help="an enabled Converse model or inference profile; "
                             "standard inference is billed")
    parser.add_argument("--tag", action="append", required=True, metavar="KEY=VALUE")
    parser.add_argument("--output", type=Path, required=True,
                        help="new receipt file; existing files are never overwritten")
    return parser.parse_args(argv)


def submitted_intent(account_id: str, expected_account_id: str, region: str, request: dict,
                     called_at: str) -> dict:
    """Return the intent saved before the call, so an uncertain response cannot repeat it."""
    return {"status": "submitted", "called_at": called_at, "account_id": account_id,
            "expected_account_id": expected_account_id, "region": region,
            "model_id": request["modelId"], "request_metadata": request["requestMetadata"],
            "vantage_verified": False}


def main(argv: list[str] | None = None) -> int:
    """Invoke once with an explicit account guard and a 16-output-token limit."""
    args = parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError(RECEIPT_EXISTS)
        request = smoke_request(args.model_id, expected_request_tags(args.tag))
        session = boto3.session.Session(region_name=args.region)
        account_id = session.client("sts").get_caller_identity()["Account"]
        if account_id != args.account_id:
            raise ValueError(f"AWS profile is account {account_id}; expected {args.account_id}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        called_at = datetime.now(timezone.utc).isoformat()
        # Save intent first: an uncertain network response must not cause a second call.
        intent = submitted_intent(account_id, args.account_id, args.region, request, called_at)
        with args.output.open("x") as output:
            output.write(json.dumps(intent, indent=2) + "\n")
        client = session.client("bedrock-runtime",
                                config=Config(retries={"total_max_attempts": 1}))
        response = client.converse(**request)
        receipt = invocation_receipt(account_id, args.region, request, response, called_at)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
        return 0
    except FileExistsError:
        print(f"FAIL {RECEIPT_EXISTS}")
        return 1
    except (ValueError, OSError, BotoCoreError, ClientError) as error:
        print(f"FAIL {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
