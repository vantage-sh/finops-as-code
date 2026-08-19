"""Plan the Bedrock logging rollout: which accounts and regions actually need it.

Run this with management-account credentials (AWS_PROFILE or your SSO
session). It is read-only: Cost Explorer says where Bedrock spend lives,
Organizations names the accounts, and the output is the exact StackSet
commands to run. All decisions live in bedrock.py; this file only fetches
and prints. Requires: pip install boto3
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from bedrock import (
    bedrock_service_names,
    deployment_blocks,
    management_account_note,
    plan_lines,
    rollout_plan,
    spend_by_account_region,
)

GLOBAL_REGION = "us-east-1"  # Cost Explorer and Organizations both live here in commercial AWS


# --- shell: AWS reads in, printed plan out -----------------------------------

def main() -> None:
    """Print where Bedrock runs and the exact commands to enable logging there."""
    args = parse_args()
    window = {"Start": (date.today() - timedelta(days=args.days)).isoformat(),
              "End": date.today().isoformat()}
    ce = boto3.client("ce", region_name=GLOBAL_REGION)

    services = bedrock_service_names(service_dimension_values(ce, window))
    if not services:
        print(f"No Bedrock service found in Cost Explorer for the last {args.days} days.")
    spend = spend_by_account_region(cost_groups(ce, window, services)) if services else []

    names, org_root, management_account, org_error = organization_roster()
    plan = rollout_plan(spend, names)

    print(f"\nBedrock spend by account and region, last {args.days} days:\n")
    print("\n".join(plan_lines(plan)) if plan["targets"] else
          "  none found; the org-wide command below still enables logging everywhere")

    for account_id in plan["multi_region_accounts"]:
        print(f"\n  note: {account_id} runs Bedrock in multiple regions. Vantage currently "
              "reads one region per account; connect the region with the most spend first.")
    note = management_account_note(plan, management_account)
    if note:
        print(f"\n{note}")

    for block in deployment_blocks(plan, org_root, org_error,
                                   args.stack_set_name, args.template_file):
        print(f"\n--- {block['title']}\n")
        print(block["body"])

    print("\nAfter deploying, run verify.py in each account, then connect the "
          "printed bucket in the Vantage UI (Settings -> AWS -> Model Invocation Logs).")


def parse_args() -> argparse.Namespace:
    """Return the parsed CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30,
                        help="Cost Explorer lookback window (default 30)")
    parser.add_argument("--stack-set-name", default="bedrock-token-allocation")
    parser.add_argument("--template-file", default="bedrock-logging.yaml")
    return parser.parse_args()


def service_dimension_values(ce: BaseClient, window: dict) -> list[str]:
    """Return every Cost Explorer SERVICE dimension value mentioning Bedrock."""
    response = ce.get_dimension_values(TimePeriod=window, Dimension="SERVICE",
                                       SearchString="Bedrock")
    return [value["Value"] for value in response["DimensionValues"]]


def cost_groups(ce: BaseClient, window: dict, services: list[str]) -> list[dict]:
    """Return the raw GetCostAndUsage periods for the Bedrock services, all pages."""
    results, token = [], None
    while True:
        kwargs = {"NextPageToken": token} if token else {}
        response = ce.get_cost_and_usage(
            TimePeriod=window, Granularity="MONTHLY", Metrics=["UnblendedCost"],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": services}},
            GroupBy=[{"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
                     {"Type": "DIMENSION", "Key": "REGION"}], **kwargs)
        results += response["ResultsByTime"]
        token = response.get("NextPageToken")
        if not token:
            return results


def organization_roster() -> tuple[dict, str | None, str | None, str]:
    """Return ({account_id: name}, org root id, management account id, why the org read failed)."""
    org = boto3.client("organizations", region_name=GLOBAL_REGION)
    management = management_account_id(org)
    try:
        pages = org.get_paginator("list_accounts").paginate()
        names = {account["Id"]: account["Name"]
                 for page in pages for account in page["Accounts"]}
        roots = org.list_roots()["Roots"]
        return names, roots[0]["Id"] if roots else None, management, ""
    except (ClientError, BotoCoreError) as error:
        return {}, None, management, str(error)


def management_account_id(org: BaseClient) -> str | None:
    """Return the organization's management account id, readable from any member account."""
    try:
        return org.describe_organization()["Organization"]["MasterAccountId"]
    except (ClientError, BotoCoreError):
        return None


if __name__ == "__main__":
    main()
