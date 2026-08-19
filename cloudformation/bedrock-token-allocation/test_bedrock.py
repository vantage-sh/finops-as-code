"""Tests for the pure core AND the template's embedded Lambdas: python3 test_bedrock.py.

Stdlib only. Both Lambda blocks are extracted straight out of
bedrock-logging.yaml and exec'd, so the code that runs in CloudFormation is
the code under test; there is no copy to drift. Path and record assertions
mirror the prefix Vantage's reader constructs and the fields it filters
and dedupes on.
"""
from __future__ import annotations

import gzip
import itertools
import json
import re
import sys
import types
from datetime import date
from pathlib import Path

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

TEMPLATE = Path(__file__).parent / "bedrock-logging.yaml"
ZIPFILE_LIMIT = 4096  # AWS::Lambda::Function inline Code.ZipFile hard cap

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


def block_at(lines: list[str], start: int) -> str:
    """Return one indented YAML literal block, dedented, starting at line index start."""
    body = itertools.takewhile(
        lambda line: not line.strip() or line.startswith(" " * 10), lines[start:])
    return "".join(line[10:] if line.startswith(" " * 10) else line for line in body)


def zipfile_blocks() -> list[str]:
    """Return every inline Lambda source block in the template, in file order."""
    lines = TEMPLATE.read_text().splitlines(keepends=True)
    starts = [i + 1 for i, line in enumerate(lines) if line.strip() == "ZipFile: |"]
    return [block_at(lines, start) for start in starts]


def exec_block(marker: str) -> dict:
    """Return the exec'd namespace of the Lambda block containing marker, stubbing boto3."""
    if "boto3" not in sys.modules:
        try:
            import boto3  # noqa: F401
        except ImportError:
            sys.modules["boto3"] = types.ModuleType("boto3")
    block = next(b for b in zipfile_blocks() if marker in b)
    namespace: dict = {}
    exec(block, namespace)
    return namespace


ENABLE = exec_block("def decide")
LOOKUP = exec_block("def vantage_role_names")


def test_both_lambdas_fit_the_inline_limit() -> None:
    """Each extracted ZipFile block stays under CloudFormation's 4096-char cap."""
    blocks = zipfile_blocks()
    assert len(blocks) == 2, "expected exactly two inline Lambdas"
    oversized = [len(block) for block in blocks if len(block) > ZIPFILE_LIMIT]
    assert not oversized, f"ZipFile block(s) at {oversized} chars will not deploy"


def test_lambda_desired_config_is_s3_only() -> None:
    """We never ask for CloudWatch delivery; all four modalities land in S3."""
    config = ENABLE["desired_config"]("my-bucket", "")
    assert config["s3Config"] == {"bucketName": "my-bucket"}
    assert "cloudWatchConfig" not in config
    enabled = [key for key, value in config.items() if value is True]
    assert sorted(enabled) == ["embeddingDataDeliveryEnabled", "imageDataDeliveryEnabled",
                               "textDataDeliveryEnabled", "videoDataDeliveryEnabled"]
    with_prefix = ENABLE["desired_config"]("my-bucket", "logs/")
    assert with_prefix["s3Config"] == {"bucketName": "my-bucket", "keyPrefix": "logs/"}


def test_lambda_decide_never_clobbers() -> None:
    """decide() puts on empty, noops on ours, and conflicts on anything else."""
    decide = ENABLE["decide"]
    ours = ENABLE["desired_config"]("my-bucket", "")
    assert decide(None, "my-bucket", "") == "put"
    assert decide({}, "my-bucket", "") == "put"
    assert decide(ours, "my-bucket", "") == "noop"
    stale_flags = dict(ours, imageDataDeliveryEnabled=False)
    assert decide(stale_flags, "my-bucket", "") == "put"
    other_bucket = {"s3Config": {"bucketName": "someone-elses"}}
    assert decide(other_bucket, "my-bucket", "") == "conflict"
    with_cloudwatch = dict(ours, cloudWatchConfig={"logGroupName": "/aws/bedrock"})
    assert decide(with_cloudwatch, "my-bucket", "") == "conflict"


def test_lambda_decide_repoints_its_own_previous_config() -> None:
    """A stack update to a new bucket recognizes the old config as its own and re-puts."""
    decide = ENABLE["decide"]
    previous = ENABLE["desired_config"]("old-bucket", "")
    assert decide(previous, "new-bucket", "", old=("old-bucket", "")) == "put"
    assert decide(previous, "new-bucket", "") == "conflict"
    someone_elses = {"s3Config": {"bucketName": "third-bucket"}}
    assert decide(someone_elses, "new-bucket", "", old=("old-bucket", "")) == "conflict"


def test_lambda_delete_guard_only_removes_our_config() -> None:
    """matches_ours() is the delete guard: only our exact S3-only config matches."""
    matches = ENABLE["matches_ours"]
    ours = ENABLE["desired_config"]("my-bucket", "")
    assert matches(ours, "my-bucket", "") is True
    assert matches(None, "my-bucket", "") is False
    assert matches({"s3Config": {"bucketName": "someone-elses"}}, "my-bucket", "") is False
    assert matches(dict(ours, cloudWatchConfig={"logGroupName": "x"}), "my-bucket", "") is False


def test_lambda_finds_only_vantage_roles() -> None:
    """Role discovery matches the ConnectToVantage naming and nothing else."""
    names = ["ConnectToVantage12345-1690000000-CrossAccountRole-AB12CD",
             "ConnectToVantage2-1784650971-CrossAccountRole-QmNjpzXG8k8A",
             "ConnectToVantageStack",  # no CrossAccountRole segment
             "MyAppRole", "cdk-hnb659fds-deploy-role"]
    assert LOOKUP["vantage_role_names"](names) == names[:2]
    assert LOOKUP["vantage_role_names"](["MyAppRole"]) == []


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


def test_deployment_blocks_pick_the_right_story() -> None:
    """Blocks cover no-org, no-spend, and the targeted case, and warn about serialization."""
    plan = rollout_plan(spend_by_account_region(CE_RESULTS), {})
    no_org = deployment_blocks(plan, None, "AccessDenied", "s", "t.yaml")
    assert len(no_org) == 1 and "AccessDenied" in no_org[0]["title"]
    assert "create-stack " in no_org[0]["body"]

    targeted = deployment_blocks(plan, "r-abc1", "", "s", "t.yaml")
    assert [block["title"].split(".")[0] for block in targeted[:2]] == ["1", "2"]
    assert "SERVICE_MANAGED" in targeted[0]["body"]
    assert "serialized" in targeted[1]["body"]
    assert "every account in the organization" in targeted[2]["title"]

    empty = deployment_blocks(rollout_plan([], {}), "r-abc1", "", "s", "t.yaml")
    assert len(empty) == 2 and "us-east-1" in empty[1]["body"]


def test_vantage_connect_values_round_trip() -> None:
    """The printed connect values carry bucket, reader prefix, and region."""
    values = vantage_connect_values("bedrock-mil-logs-123456789012-us-east-1",
                                    "123456789012", "us-east-1")
    assert values == {
        "bucket": "bedrock-mil-logs-123456789012-us-east-1",
        "prefix": "AWSLogs/123456789012/BedrockModelInvocationLogs/us-east-1/",
        "region": "us-east-1",
    }


def test_record_problems_mirror_the_reader_rules() -> None:
    """A real record passes; the fields Vantage filters or dedupes on are enforced."""
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
    assert "SERVICE_MANAGED" in create and "Enabled=true" in create
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
