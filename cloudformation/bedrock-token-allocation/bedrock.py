"""Pure helpers for planning and verifying Bedrock Model Invocation Logging.

Everything in this module is pure: data in, data out, no AWS calls. The
shells live in preflight.py (plan the rollout) and verify.py (prove one
account works). Path and record rules mirror what Vantage's reader
expects, so a green verify.py means Vantage can ingest the logs.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date, timedelta

REQUIRED_RECORD_FIELDS = ("schemaType", "timestamp", "accountId", "region",
                          "requestId", "operation", "modelId")


# --- core: pure functions, data in, data out ---------------------------------

def log_prefix(account_id: str, region: str, key_prefix: str = "") -> str:
    """Return the S3 prefix Bedrock writes to and Vantage reads from, with trailing slash."""
    base = f"AWSLogs/{account_id}/BedrockModelInvocationLogs/{region}/"
    return f"{key_prefix.strip('/')}/{base}" if key_prefix.strip("/") else base


def vantage_connect_values(bucket: str, account_id: str, region: str,
                           key_prefix: str = "") -> dict:
    """Return the exact bucket, prefix, and region to enter in the Vantage UI."""
    return {
        "bucket": bucket,
        "prefix": log_prefix(account_id, region, key_prefix),
        "region": region,
    }


def object_key_pattern(account_id: str, region: str, key_prefix: str = "") -> str:
    """Return a regex matching invocation-record keys only, never the data/ payload objects."""
    prefix = re.escape(log_prefix(account_id, region, key_prefix))
    # YYYY/MM/DD/HH/<one filename>: [^/]+ is what excludes the data/ subtree,
    # where Bedrock puts request and response bodies over 100 KB.
    return rf"{prefix}\d{{4}}/\d{{2}}/\d{{2}}/\d{{2}}/[^/]+\.json\.gz"


def day_prefixes(prefix: str, today: date, days: int) -> list[str]:
    """Return the S3 prefixes for the last N days, newest first."""
    return [f"{prefix}{(today - timedelta(days=offset)):%Y/%m/%d}/" for offset in range(days)]


def record_problems(record: dict) -> list[str]:
    """Return the reasons Vantage's reader would drop this log record; empty means it joins."""
    problems = [
        f"{field} is missing or blank"
        for field in REQUIRED_RECORD_FIELDS
        if not str(record.get(field) or "").strip()
    ]
    schema = record.get("schemaType")
    if schema and schema != "ModelInvocationLog":
        problems.append(f"schemaType {schema!r} is filtered out; only ModelInvocationLog rows join")
    return problems


def record_warnings(record: dict) -> list[str]:
    """Return non-fatal gaps: the record joins, but with less attribution than it could."""
    if record.get("requestMetadata"):
        return []
    return ["no requestMetadata: spend still splits by principal and model, "
            "but none of your team/app/env tags (see the README section)"]


def records_from_gz(body: bytes) -> list[dict]:
    """Return the JSON records inside a .json.gz body (one per line, or a single object)."""
    text = gzip.decompress(body).decode("utf-8").strip()
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        return [json.loads(line) for line in lines]
    except json.JSONDecodeError:
        return [json.loads(text)]


def bedrock_service_names(all_services: list[str]) -> list[str]:
    """Return the Cost Explorer service names that are Bedrock, marketplace models included."""
    return [name for name in all_services if "Bedrock" in name]


def resolved_region(explicit: str | None, env: dict) -> str | None:
    """Return the region the AWS CLI would use: --region, then AWS_REGION, then AWS_DEFAULT_REGION."""
    for value in (explicit, env.get("AWS_REGION"), env.get("AWS_DEFAULT_REGION")):
        if value and value.strip():
            return value.strip()
    return None


def deployable_region(region: str) -> bool:
    """Return True for a real region code; Cost Explorer also emits NoRegion and global."""
    return bool(re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d+", region))


def spend_by_account_region(results_by_time: list[dict]) -> list[dict]:
    """Return summed Bedrock cost per (account, region) from a GetCostAndUsage response, largest first."""
    grouped = [
        (group["Keys"][0], group["Keys"][1],
         float(group["Metrics"]["UnblendedCost"]["Amount"]))
        for period in results_by_time
        for group in period.get("Groups", [])
    ]
    totals: dict[tuple[str, str], float] = {}
    for account_id, region, cost in grouped:
        totals[(account_id, region)] = totals.get((account_id, region), 0.0) + cost
    rows = [
        {"account_id": account_id, "region": region, "cost": cost}
        for (account_id, region), cost in totals.items()
        if cost >= 0.01 and deployable_region(region)
    ]
    return sorted(rows, key=lambda row: -row["cost"])


def rollout_plan(spend: list[dict], account_names: dict) -> dict:
    """Return the deploy plan: one target per account with its regions, primary region first."""
    by_account: dict[str, list[dict]] = {}
    for row in spend:
        by_account.setdefault(row["account_id"], []).append(row)
    targets = [
        {
            "account_id": account_id,
            "name": account_names.get(account_id, ""),
            "regions": [{"region": r["region"], "cost": r["cost"]}
                        for r in sorted(rows, key=lambda r: -r["cost"])],
            "primary_region": max(rows, key=lambda r: r["cost"])["region"],
            "cost": round(sum(r["cost"] for r in rows), 2),
        }
        for account_id, rows in by_account.items()
    ]
    targets.sort(key=lambda t: -t["cost"])
    return {
        "targets": targets,
        "regions": sorted({row["region"] for row in spend}),
        "multi_region_accounts": [t["account_id"] for t in targets if len(t["regions"]) > 1],
    }


def stackset_create_command(stack_set_name: str, template_file: str) -> str:
    """Return the CLI that creates the service-managed, auto-deploying stack set."""
    return (f"aws cloudformation create-stack-set \\\n"
            f"  --stack-set-name {stack_set_name} \\\n"
            f"  --template-body file://{template_file} \\\n"
            f"  --permission-mode SERVICE_MANAGED \\\n"
            f"  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=true \\\n"
            f"  --capabilities CAPABILITY_IAM")


def stackset_instances_command(stack_set_name: str, org_root_id: str,
                               regions: list[str],
                               account_ids: list[str] | None = None) -> str:
    """Return the CLI that deploys stack instances org-wide, or only to the listed accounts."""
    targets = f"OrganizationalUnitIds={org_root_id}"
    if account_ids:
        targets += f",AccountFilterType=INTERSECTION,Accounts={','.join(account_ids)}"
    return (f"aws cloudformation create-stack-instances \\\n"
            f"  --stack-set-name {stack_set_name} \\\n"
            f"  --regions {' '.join(regions)} \\\n"
            f"  --deployment-targets {targets} \\\n"
            f"  --operation-preferences FailureToleranceCount=1,MaxConcurrentCount=10,"
            f"ConcurrencyMode=SOFT_FAILURE_TOLERANCE")


def targeted_instance_commands(stack_set_name: str, org_root_id: str,
                               plan: dict) -> list[str]:
    """Return one create-stack-instances per region, each limited to the accounts with spend there."""
    pairs = [(row["region"], target["account_id"])
             for target in plan["targets"] for row in target["regions"]]
    by_region: dict[str, list[str]] = {}
    for region, account_id in pairs:
        by_region.setdefault(region, []).append(account_id)
    return [stackset_instances_command(stack_set_name, org_root_id, [region], accounts)
            for region, accounts in sorted(by_region.items())]


def management_account_note(plan: dict, management_account: str | None) -> str:
    """Return a warning when a target is the management account, which StackSets skip."""
    ids = [target["account_id"] for target in plan["targets"]]
    if not management_account or management_account not in ids:
        return ""
    return (f"  note: {management_account} is your organization's management account. "
            "Service-managed StackSets never deploy to it, so run the single-account "
            "stack there separately.")


def deployment_blocks(plan: dict, org_root: str | None, org_error: str,
                      stack_set_name: str, template_file: str) -> list[dict]:
    """Return the {title, body} blocks describing how to deploy, given what we could read."""
    if not org_root:
        return [{"title": f"Could not read your AWS Organization: {org_error}",
                 "body": "The org-wide commands need management-account credentials. "
                         "To deploy one account at a time:\n\n"
                         f"aws cloudformation create-stack \\\n"
                         f"  --stack-name bedrock-token-allocation \\\n"
                         f"  --template-body file://{template_file} \\\n"
                         f"  --capabilities CAPABILITY_IAM"}]
    create = {"title": "1. Create the stack set (run once, in the management account)",
              "body": stackset_create_command(stack_set_name, template_file)}
    if not plan["targets"]:
        return [create, {"title": "2. Deploy instances",
                         "body": stackset_instances_command(stack_set_name, org_root,
                                                            ["us-east-1"])}]
    targeted = targeted_instance_commands(stack_set_name, org_root, plan)
    return [
        create,
        {"title": f"2. Deploy instances where Bedrock spend showed, {len(targeted)} "
                  "operation(s), one per region",
         "body": "\n\n".join(targeted) + "\n\nStack set operations are serialized: wait for "
                 "each to reach SUCCEEDED (aws cloudformation describe-stack-set-operation) "
                 "before starting the next, or the second is rejected."},
        {"title": "Or every account in the organization, including ones created later",
         "body": stackset_instances_command(stack_set_name, org_root, plan["regions"])},
    ]


def plan_lines(plan: dict) -> list[str]:
    """Return the printable spend table: an account line, then one line per region."""
    def target_block(target: dict) -> list[str]:
        """Return the lines for one account and its regions."""
        label = f" ({target['name']})" if target["name"] else ""
        head = f"  {target['account_id']}{label}  ${target['cost']:,.2f}"
        return [head] + [f"      {row['region']:<16} ${row['cost']:,.2f}"
                         for row in target["regions"]]
    return [line for target in plan["targets"] for line in target_block(target)]


def logging_status_line(config: dict | None) -> str:
    """Return a one-line human summary of a GetModelInvocationLoggingConfiguration result."""
    if not config:
        return "logging is OFF"
    s3 = config.get("s3Config") or {}
    destination = s3.get("bucketName", "(no S3 destination)")
    cloudwatch = " + CloudWatch" if config.get("cloudWatchConfig") else ""
    return f"logging is ON -> s3://{destination}{cloudwatch}"
