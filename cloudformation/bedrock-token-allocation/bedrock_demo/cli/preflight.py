"""Plan the Bedrock logging rollout: which accounts and regions actually need it.

Run this with management-account credentials (AWS_PROFILE or your SSO
session). It is read-only: Cost Explorer says where Bedrock spend lives,
Organizations names the accounts, and the output is the exact StackSet
commands to run. Planning rules live in core/planning.py; AWS reads live in
aws/discovery.py. Requires: pip install boto3
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import boto3

from bedrock_demo.aws.discovery import (
    GLOBAL_REGION,
    cost_groups,
    organization_roster,
    service_dimension_values,
)
from bedrock_demo.core.planning import (
    bedrock_service_names,
    deployment_blocks,
    management_account_note,
    plan_lines,
    rollout_plan,
    spend_by_account_region,
)

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
          "  none found; no fixed-account deployment targets inferred")

    for account_id in plan["multi_region_accounts"]:
        print(f"\n  note: {account_id} runs Bedrock in multiple regions. Connect each "
              "original regional bucket in Vantage to cover all of this usage.")
    note = management_account_note(plan, management_account)
    if note:
        print(f"\n{note}")

    for block in deployment_blocks(plan, args.ou_id or org_root, org_error,
                                   args.stack_set_name, args.template_file, args.mode):
        print(f"\n--- {block['title']}\n")
        print(block["body"])

    print("\nAfter deploying, run verify.py in each account, then connect the "
          "original bucket in Vantage (Settings -> Integrations -> AWS Bedrock). "
          "Complete Check Permissions, Import History, and account/tag cost checks there.")


def parse_args() -> argparse.Namespace:
    """Return the parsed CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=30,
                        help="Cost Explorer lookback window (default 30)")
    parser.add_argument("--stack-set-name", default="bedrock-token-allocation")
    parser.add_argument("--template-file", default="bedrock-logging.yaml")
    parser.add_argument("--mode", choices=("fixed", "ou"), default="fixed")
    parser.add_argument("--ou-id", help="Explicit OU/root for future-account auto-deployment")
    args = parser.parse_args()
    if args.days < 1 or args.days > 366:
        parser.error("--days must be between 1 and 366")
    if args.mode == "ou" and not args.ou_id:
        parser.error("--mode ou requires an explicit --ou-id")
    return args


if __name__ == "__main__":
    main()
