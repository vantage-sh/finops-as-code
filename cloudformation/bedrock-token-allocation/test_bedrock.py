"""Stdlib tests for native log contracts and explicit deployment plans: python3 test_bedrock.py.

Lambda lifecycle and generated-template tests live under tests/. These checks
exercise the public demo helpers; they do not run Vantage Core or prove ingestion.
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date

from bedrock import (
    bedrock_service_names,
    day_prefixes,
    deployable_region,
    deployment_blocks,
    management_account_note,
    log_prefix,
    logging_status_line,
    object_key_pattern,
    plan_lines,
    record_problems,
    record_warnings,
    records_from_gz,
    resolved_region,
    rollout_plan,
    spend_by_account_region,
    stackset_create_command,
    stackset_instances_command,
    targeted_instance_commands,
    vantage_connect_values,
)

MIL_RECORD = {
    "schemaType": "ModelInvocationLog",
    "timestamp": "2026-08-19T12:00:00Z",
    "accountId": "123456789012",
    "identity": {"arn": "arn:aws:sts::123456789012:assumed-role/checkout-api"},
    "region": "us-east-1",
    "requestId": "3f0e2c9d-example",
    "operation": "Converse",
    "modelId": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-5",
    "input": {"inputContentType": "application/json", "inputTokenCount": 1268},
    "output": {"outputContentType": "application/json", "outputTokenCount": 312},
    "requestMetadata": {"team": "growth", "environment": "prod"},
}

CE_RESULTS = [
    {"Groups": [
        {"Keys": ["111111111111", "us-east-1"],
         "Metrics": {"UnblendedCost": {"Amount": "1200.50", "Unit": "USD"}}},
        {"Keys": ["222222222222", "us-west-2"],
         "Metrics": {"UnblendedCost": {"Amount": "80.25", "Unit": "USD"}}},
        {"Keys": ["111111111111", "NoRegion"],
         "Metrics": {"UnblendedCost": {"Amount": "42.00", "Unit": "USD"}}},
    ]},
    {"Groups": [
        {"Keys": ["111111111111", "us-east-1"],
         "Metrics": {"UnblendedCost": {"Amount": "300.00", "Unit": "USD"}}},
        {"Keys": ["111111111111", "eu-west-1"],
         "Metrics": {"UnblendedCost": {"Amount": "10.00", "Unit": "USD"}}},
        {"Keys": ["333333333333", "us-east-1"],
         "Metrics": {"UnblendedCost": {"Amount": "0.00", "Unit": "USD"}}},
        {"Keys": ["222222222222", "global"],
         "Metrics": {"UnblendedCost": {"Amount": "5.00", "Unit": "USD"}}},
    ]},
]


def test_log_prefix_matches_the_vantage_reader() -> None:
    """The prefix is exactly what Vantage constructs: AWSLogs/<acct>/BedrockModelInvocationLogs/<region>/."""
    assert log_prefix("123456789012", "us-east-1") == \
        "AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/"
    assert log_prefix("123456789012", "us-east-1", "audit/") == \
        "audit/AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/"


def test_object_key_pattern_accepts_real_delivery_keys() -> None:
    """Bedrock's date/hour-partitioned .json.gz keys match; strays do not."""
    pattern = object_key_pattern("123456789012", "us-east-1")
    good = ("AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/"
            "2026/08/19/05/8d7f2a-invocation.json.gz")
    assert re.fullmatch(pattern, good)
    assert not re.fullmatch(pattern, good.replace(".json.gz", ".parquet"))
    assert not re.fullmatch(pattern, good.replace("123456789012", "999999999999"))


def test_object_key_pattern_excludes_large_payload_objects() -> None:
    """Bedrock's data/ payload objects are .json.gz too, and must not count as records."""
    pattern = object_key_pattern("123456789012", "us-east-1")
    base = "AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/2026/06/06/07"
    assert re.fullmatch(pattern, f"{base}/20260606T070102Z_9f2a.json.gz")
    assert not re.fullmatch(pattern, f"{base}/data/3f0e2c9d-example_input.json.gz")
    assert not re.fullmatch(pattern, f"{base}/data/3f0e2c9d-example_output.json.gz")
    assert not re.fullmatch(pattern, f"{base}/amazon-bedrock-logs-permission-check")


def test_day_prefixes_walk_backwards_from_today() -> None:
    """Day prefixes are newest first and match Bedrock's YYYY/MM/DD partitioning."""
    prefixes = day_prefixes("AWSLogs/1/BedrockModelInvocationLogs/us-east-1/",
                            date(2026, 3, 1), 3)
    assert prefixes == [
        "AWSLogs/1/BedrockModelInvocationLogs/us-east-1/2026/03/01/",
        "AWSLogs/1/BedrockModelInvocationLogs/us-east-1/2026/02/28/",
        "AWSLogs/1/BedrockModelInvocationLogs/us-east-1/2026/02/27/",
    ]


def test_management_account_note_only_when_targeted() -> None:
    """The warning appears only when the management account is itself a deploy target."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    assert management_account_note(plan, "111111111111").startswith("  note: 111111111111")
    assert management_account_note(plan, "999999999999") == ""
    assert management_account_note(plan, None) == ""


def test_fixed_deployment_blocks_do_not_enroll_future_accounts() -> None:
    """Fixed targeting covers only observed account-region pairs and disables auto-enrollment."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    blocks = deployment_blocks(plan, "r-abc1", "", "s", "t.yaml")
    assert len(blocks) == 2
    assert "--permission-model SERVICE_MANAGED" in blocks[0]["body"]
    assert "Enabled=false,RetainStacksOnAccountRemoval=true" in blocks[0]["body"]
    assert "Accounts=111111111111" in blocks[1]["body"]
    assert "Accounts=222222222222" in blocks[1]["body"]
    assert "serialized" in blocks[1]["body"]


def test_ou_deployment_explicitly_enrolls_future_accounts() -> None:
    """An explicit OU mode covers the selected OU with future-account auto-deployment."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    blocks = deployment_blocks(plan, "ou-abcd-example", "", "s", "t.yaml", mode="ou")
    assert len(blocks) == 2
    assert "Enabled=true,RetainStacksOnAccountRemoval=true" in blocks[0]["body"]
    assert "OrganizationalUnitIds=ou-abcd-example" in blocks[1]["body"]
    assert "Accounts=" not in blocks[1]["body"]
    assert "--regions eu-west-1 us-east-1 us-west-2" in blocks[1]["body"]


def test_empty_spend_does_not_expand_fixed_rollout_to_the_organization() -> None:
    """Empty fixed-target discovery stops instead of inventing organization-wide coverage."""
    blocks = deployment_blocks(rollout_plan([], {}), "r-abc1", "", "s", "t.yaml")
    assert blocks == [{
        "title": "No fixed-account targets found",
        "body": "Provide explicit accounts with deploy.py or select --mode ou --ou-id. "
                "No organization-wide deployment is inferred from empty spend.",
    }]


def test_missing_organization_access_returns_a_local_stack_fallback() -> None:
    """Failure to read Organizations never becomes a successful org deployment plan."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    blocks = deployment_blocks(plan, None, "AccessDenied", "s", "t.yaml")
    assert len(blocks) == 1
    assert "AccessDenied" in blocks[0]["title"]
    assert "create-stack " in blocks[0]["body"]
    assert "CAPABILITY_NAMED_IAM" in blocks[0]["body"]
    assert "create-stack-instances" not in blocks[0]["body"]


def test_vantage_connect_values_round_trip() -> None:
    """The printed connect values carry bucket, reader prefix, and region."""
    values = vantage_connect_values("bedrock-mil-logs-123456789012-us-east-1",
                                    "123456789012", "us-east-1")
    assert values == {
        "bucket": "bedrock-mil-logs-123456789012-us-east-1",
        "prefix": "AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/",
        "region": "us-east-1",
    }


def test_record_problems_require_the_demo_native_fixture_fields() -> None:
    """A native AWS fixture passes the demo readiness checks; incomplete samples fail."""
    assert record_problems(MIL_RECORD) == []
    wrong_schema = dict(MIL_RECORD, schemaType="ModelInvocationEvent")
    assert any("filtered out" in problem for problem in record_problems(wrong_schema))
    no_request_id = {k: v for k, v in MIL_RECORD.items() if k != "requestId"}
    assert any("requestId" in problem for problem in record_problems(no_request_id))
    null_operation = dict(MIL_RECORD, operation=None)
    assert any("operation" in problem for problem in record_problems(null_operation))


def test_record_warnings_flag_missing_metadata() -> None:
    """No requestMetadata is a warning (spend still joins), never a failure."""
    assert record_warnings(MIL_RECORD) == []
    untagged = {k: v for k, v in MIL_RECORD.items() if k != "requestMetadata"}
    assert len(record_warnings(untagged)) == 1
    assert record_problems(untagged) == []


def test_records_from_gz_reads_both_shapes() -> None:
    """Both one-JSON-per-line and single-object gzip bodies parse."""
    line = json.dumps(MIL_RECORD)
    assert len(records_from_gz(gzip.compress(f"{line}\n{line}\n".encode()))) == 2
    pretty = json.dumps(MIL_RECORD, indent=2)
    assert records_from_gz(gzip.compress(pretty.encode())) == [MIL_RECORD]


def test_current_core_native_wire_contract_preserves_origin_and_customer_tags() -> None:
    """The fixture stays native Bedrock JSON and points Vantage at the original calling region."""
    record = dict(MIL_RECORD, modelId="us.amazon.nova-micro-v1:0", inferenceRegion="us-west-2")
    decoded = records_from_gz(gzip.compress(json.dumps(record).encode()))[0]
    assert decoded["accountId"] == "123456789012"
    assert decoded["region"] == "us-east-1"
    assert decoded["inferenceRegion"] == "us-west-2"
    assert decoded["requestMetadata"] == {"team": "growth", "environment": "prod"}
    assert "resource_account_id" not in decoded
    assert "tags" not in decoded
    assert vantage_connect_values("original-bucket", decoded["accountId"], decoded["region"]) == {
        "bucket": "original-bucket",
        "prefix": "AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/",
        "region": "us-east-1",
    }


def test_resolved_region_follows_cli_precedence() -> None:
    """The flag wins, then AWS_REGION, then AWS_DEFAULT_REGION, matching the AWS CLI."""
    assert resolved_region("eu-west-1", {"AWS_REGION": "us-east-1"}) == "eu-west-1"
    both = {"AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "eu-west-1"}
    assert resolved_region(None, both) == "us-east-1"
    assert resolved_region(None, {"AWS_DEFAULT_REGION": "eu-west-1"}) == "eu-west-1"
    assert resolved_region(None, {}) is None
    assert resolved_region(None, {"AWS_REGION": "   "}) is None
    assert resolved_region(None, {"AWS_REGION": " us-east-1 "}) == "us-east-1"


def test_deployable_region_rejects_cost_explorer_sentinels() -> None:
    """Real region codes pass; Cost Explorer's NoRegion/global rows never do."""
    assert deployable_region("us-east-1")
    assert deployable_region("ap-southeast-3")
    assert not deployable_region("NoRegion")
    assert not deployable_region("global")
    assert not deployable_region("")


def test_spend_aggregates_and_filters_non_regions() -> None:
    """Costs sum per (account, region); zero and NoRegion/global rows drop; biggest first."""
    rows = spend_by_account_region(CE_RESULTS)
    assert rows[0] == {"account_id": "111111111111", "region": "us-east-1", "cost": 1500.5}
    regions = {row["region"] for row in rows}
    assert "NoRegion" not in regions and "global" not in regions
    assert len(rows) == 3


def test_rollout_plan_flags_multi_region_accounts() -> None:
    """The plan groups by account, picks the top-spend region, and flags multi-region."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {"111111111111": "prod"})
    top = plan["targets"][0]
    assert top["account_id"] == "111111111111" and top["name"] == "prod"
    assert top["primary_region"] == "us-east-1"
    assert plan["multi_region_accounts"] == ["111111111111"]
    assert plan["regions"] == ["eu-west-1", "us-east-1", "us-west-2"]


def test_plan_lines_render_the_spend_table() -> None:
    """One line per account, indented lines per region, dollars formatted."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {"111111111111": "prod"})
    lines = plan_lines(plan)
    assert lines[0] == "  111111111111 (prod)  $1,510.50"
    assert lines[1].strip().startswith("us-east-1") and "$1,500.50" in lines[1]


def test_stackset_commands_carry_the_org_mechanics() -> None:
    """Service-managed permissions, auto-deploy, soft failure mode, and targeting are present."""
    create = stackset_create_command("bedrock-token-allocation", "bedrock-logging.yaml")
    assert "--permission-model SERVICE_MANAGED" in create
    assert "Enabled=false,RetainStacksOnAccountRemoval=true" in create
    assert "CAPABILITY_NAMED_IAM" in create
    org_wide = stackset_instances_command("s", "r-abc1", ["us-east-1", "eu-west-1"])
    assert "OrganizationalUnitIds=r-abc1" in org_wide and "Accounts=" not in org_wide
    assert "ConcurrencyMode=SOFT_FAILURE_TOLERANCE" in org_wide
    targeted = stackset_instances_command("s", "r-abc1", ["us-east-1"], ["111111111111"])
    assert "AccountFilterType=INTERSECTION,Accounts=111111111111" in targeted


def test_targeted_commands_avoid_the_region_cross_product() -> None:
    """Each region's command lists only the accounts that showed spend in that region."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    commands = targeted_instance_commands("s", "r-abc1", plan)
    assert len(commands) == 3
    by_region = {re.search(r"--regions (\S+)", cmd).group(1): cmd for cmd in commands}
    assert "Accounts=111111111111" in by_region["eu-west-1"]
    assert "222222222222" not in by_region["eu-west-1"]
    assert "Accounts=222222222222" in by_region["us-west-2"]


def test_bedrock_service_names_catch_marketplace_models() -> None:
    """Native and marketplace Bedrock services both count; others never do."""
    services = ["Amazon Bedrock", "Claude Sonnet 4.5 (Amazon Bedrock Edition)",
                "Amazon Elastic Compute Cloud - Compute"]
    assert bedrock_service_names(services) == services[:2]


def test_logging_status_lines_read_cleanly() -> None:
    """The status line names the destination and flags CloudWatch double-delivery."""
    assert logging_status_line(None) == "logging is OFF"
    s3_only = {"s3Config": {"bucketName": "b"}}
    assert logging_status_line(s3_only) == "logging is ON -> s3://b"
    both = dict(s3_only, cloudWatchConfig={"logGroupName": "x"})
    assert logging_status_line(both).endswith("+ CloudWatch")


if __name__ == "__main__":
    tests = [value for key, value in sorted(globals().items()) if key.startswith("test_")]
    for test in tests:
        test()
        print(f"ok   {test.__name__}")
    print(f"PASS {len(tests)} tests")
