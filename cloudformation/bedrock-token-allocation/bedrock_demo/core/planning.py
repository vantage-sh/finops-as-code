"""Pure spend-based deployment plans and explicit StackSet targeting."""
from __future__ import annotations

import re
import shlex


def bedrock_service_names(all_services: list[str]) -> list[str]:
    """Return the Cost Explorer service names that are Bedrock, marketplace models included."""
    return [name for name in all_services if "Bedrock" in name]


def deployable_region(region: str) -> bool:
    """Return True for a real region code; Cost Explorer also emits NoRegion and global."""
    return bool(re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d+", region))


def spend_by_account_region(results_by_time: list[dict]) -> list[dict]:
    """Return summed Bedrock cost per (account, region) from Cost Explorer, largest first."""
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


def stackset_create_command(stack_set_name: str, template_file: str,
                            auto_deploy: bool = False) -> str:
    """Return a StackSet command with future-account enrollment explicitly selected."""
    enrollment = "true" if auto_deploy else "false"
    return (f"aws cloudformation create-stack-set \\\n"
            f"  --stack-set-name {shlex.quote(stack_set_name)} \\\n"
            f"  --template-body {shlex.quote('file://' + template_file)} \\\n"
            f"  --permission-model SERVICE_MANAGED \\\n"
            f"  --auto-deployment Enabled={enrollment},RetainStacksOnAccountRemoval=true \\\n"
            f"  --capabilities CAPABILITY_NAMED_IAM")


def stackset_instances_command(stack_set_name: str, org_root_id: str,
                               regions: list[str],
                               account_ids: list[str] | None = None) -> str:
    """Return the CLI that deploys stack instances org-wide, or only to the listed accounts."""
    targets = f"OrganizationalUnitIds={org_root_id}"
    if account_ids:
        targets += f",AccountFilterType=INTERSECTION,Accounts={','.join(account_ids)}"
    return (f"aws cloudformation create-stack-instances \\\n"
            f"  --stack-set-name {shlex.quote(stack_set_name)} \\\n"
            f"  --regions {' '.join(shlex.quote(region) for region in regions)} \\\n"
            f"  --deployment-targets {shlex.quote(targets)} \\\n"
            f"  --operation-preferences FailureToleranceCount=1,MaxConcurrentCount=10,"
            f"ConcurrencyMode=SOFT_FAILURE_TOLERANCE")


def targeted_instance_commands(stack_set_name: str, org_root_id: str,
                               plan: dict) -> list[str]:
    """Return one create-stack-instances per region, limited to the accounts with spend there."""
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
                      stack_set_name: str, template_file: str,
                      mode: str = "fixed") -> list[dict]:
    """Return the {title, body} blocks describing how to deploy, given what we could read."""
    if not org_root:
        return [{"title": f"Could not read your AWS Organization: {org_error}",
                 "body": "The org-wide commands need management-account credentials. "
                         "To deploy one account at a time:\n\n"
                         f"aws cloudformation create-stack \\\n"
                         f"  --stack-name bedrock-token-allocation \\\n"
                         f"  --template-body {shlex.quote('file://' + template_file)} \\\n"
                         f"  --capabilities CAPABILITY_NAMED_IAM"}]
    create = {"title": "1. Create the stack set (run once, in the management account)",
              "body": stackset_create_command(stack_set_name, template_file, mode == "ou")}
    if mode == "ou":
        return [create, {"title": "2. Deploy to the selected OU, including future accounts",
                         "body": stackset_instances_command(stack_set_name, org_root,
                                                            plan["regions"] or ["us-east-1"])}]
    if not plan["targets"]:
        return [{"title": "No fixed-account targets found",
                 "body": "Provide explicit accounts with deploy.py or select --mode ou --ou-id. "
                         "No organization-wide deployment is inferred from empty spend."}]
    targeted = targeted_instance_commands(stack_set_name, org_root, plan)
    return [
        create,
        {"title": f"2. Deploy instances where Bedrock spend showed, {len(targeted)} "
                  "operation(s), one per region",
         "body": "\n\n".join(targeted) + "\n\nStack set operations are serialized: wait for "
                 "each to reach SUCCEEDED (aws cloudformation describe-stack-set-operation) "
                 "before starting the next, or the second is rejected."},
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
