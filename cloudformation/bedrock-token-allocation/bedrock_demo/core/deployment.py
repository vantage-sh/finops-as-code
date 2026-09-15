"""Pure deployment configuration, identity guards, and resumable manifest state."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from bedrock_demo.core.logs import log_prefix
from bedrock_demo.core.planning import deployable_region

TEMPLATE_NAMES = ("bedrock-central-bucket.yaml", "bedrock-logging.yaml")


def config_problems(config: dict) -> list[str]:
    """Return unsafe or unsupported rollout inputs before any AWS mutation."""
    if config.get("version") != 1:
        return ["config version must be 1"]
    deployment_id = config.get("deployment_id", "")
    if not isinstance(deployment_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,27}",
                                                               deployment_id):
        return ["deployment_id must be 3-28 lowercase letters, digits, or hyphens"]
    sources = config.get("sources")
    if (not isinstance(config.get("central"), dict) or not isinstance(sources, list)
            or not sources or any(not isinstance(s, dict) for s in sources)):
        return ["one central destination and at least one source are required"]
    entries = [config["central"], *sources]
    problems = [problem for entry in entries for problem in entry_problems(entry)]
    if problems:
        return problems
    if len({region_partition(entry["region"]) for entry in entries}) != 1:
        problems.append("source and central regions must belong to the same AWS partition")
    central_kms = config["central"].get("kms", False)
    if type(central_kms) is not bool:
        problems.append("central.kms must be true or false")
    if any(bool(s.get("kms_key_arn")) != central_kms for s in sources):
        problems.append("KMS replication requires central.kms=true and a kms_key_arn on every "
                        "source; otherwise use SSE-S3 throughout")
    pairs = [(entry.get("account_id"), entry.get("region")) for entry in sources]
    if len(pairs) != len(set(pairs)):
        problems.append("only one source per account and region is allowed")
    buckets = [entry.get("bucket_name") for entry in entries]
    if len(buckets) != len(set(buckets)):
        problems.append("source and central bucket names must all differ")
    stacks = [(e.get("account_id"), e.get("region"), e.get("stack_name")) for e in entries]
    if len(stacks) != len(set(stacks)):
        problems.append("stack account/region/name combinations must be unique")
    return problems + [problem for source in sources for problem in source_problems(source)]


def entry_problems(entry: dict) -> list[str]:
    """Return malformed account, region, stack, or bucket fields."""
    problems = []
    account_id = entry.get("account_id", "")
    if not isinstance(account_id, str) or not re.fullmatch(r"\d{12}", account_id):
        problems.append("each account_id must contain 12 digits")
    region = entry.get("region", "")
    if not isinstance(region, str) or not deployable_region(region):
        problems.append("each entry needs an explicit AWS region")
    elif region_partition(region) is None:
        problems.append("region must belong to the aws, aws-cn, or aws-us-gov partition")
    stack_name = entry.get("stack_name", "")
    if not isinstance(stack_name, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]{0,127}",
                                                            stack_name):
        problems.append("each stack_name must start with a letter and use letters/digits/hyphens")
    bucket = entry.get("bucket_name", "")
    if not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        problems.append("use a 3-63 character bucket_name with lowercase letters/digits/dots/hyphens")
    elif ".." in bucket:
        problems.append("bucket_name must not contain adjacent dots")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", bucket):
        problems.append("bucket_name must not be formatted as an IP address")
    elif bucket.endswith(".mrap"):
        problems.append("bucket_name must not end with the reserved .mrap suffix")
    retention = entry.get("retention_days", 0)
    if type(retention) is not int or not 0 <= retention <= 3650:
        problems.append("retention_days must be an integer from 0 to 3650; 0 retains data")
    if entry.get("profile") is not None and not isinstance(entry.get("profile"), str):
        problems.append("profile must be an AWS profile name")
    return problems


def region_partition(region: str) -> str | None:
    """Resolve supported AWS partition patterns without assuming unknown regions are commercial."""
    patterns = {"aws": r"(?:us|eu|ap|sa|ca|me|af|il|mx)-[a-z]+-\d+",
                "aws-cn": r"cn-[a-z]+-\d+", "aws-us-gov": r"us-gov-[a-z]+-\d+"}
    return next((partition for partition, pattern in patterns.items()
                 if re.fullmatch(pattern, region)), None)


def source_problems(source: dict) -> list[str]:
    """Return source options unsupported by the managed replication wrapper."""
    problems = []
    if source.get("logging_mode", "Managed") != "Managed":
        problems.append("deploy.py manages new source buckets; use the template's Reuse mode "
                        "for existing buckets")
    prefix = source.get("key_prefix", "")
    if (not isinstance(prefix, str)
            or (prefix and (not prefix.endswith("/") or prefix.startswith("/")))):
        problems.append("key_prefix must be empty or end with / without a leading /")
    if not isinstance(source.get("vantage_role", ""), str):
        problems.append("vantage_role must be a role name string, or omitted to discover one")
    if not isinstance(source.get("kms_key_arn", ""), str):
        problems.append("kms_key_arn must be a KMS key ARN string, or omitted for SSE-S3")
    return problems


def fingerprint(value: dict) -> str:
    """Return a stable digest of JSON data for manifest integrity checks."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def template_hashes(bodies: dict) -> dict:
    """Hash saved template text without reading the working tree."""
    return {name: hashlib.sha256(body.encode()).hexdigest() for name, body in bodies.items()}


def manifest_problems(manifest: dict) -> list[str]:
    """Return mismatched saved intent or templates before a deployment can resume."""
    config = manifest.get("config", {})
    problems = config_problems(config)
    if manifest.get("version") != 1 or problems:
        return ["Invalid manifest version or config", *problems]
    if manifest.get("config_hash") != fingerprint(config):
        return ["Manifest config changed; create a fresh reviewed plan instead"]
    templates = manifest.get("template_bodies", {})
    if set(templates) != set(TEMPLATE_NAMES):
        return ["Manifest is missing its reviewed template snapshots; "
                "do not substitute new templates"]
    if manifest.get("template_hashes") != template_hashes(templates):
        return ["Saved template snapshots changed after planning"]
    units = manifest.get("units", [])
    intended = deployment_units(config)
    if len(units) != len(intended):
        return ["Manifest deployment units changed"]
    if any(unit_drifted(unit, intent) for unit, intent in zip(units, intended)):
        return ["Manifest stack intent changed"]
    return []


def unit_drifted(unit: dict, intent: dict) -> bool:
    """Return whether any planned field of a saved unit differs from the config's intent."""
    return any(unit.get(key) != value for key, value in intent.items())


def deployment_units(config: dict) -> list[dict]:
    """Return central-first stack intents with account-specific source parameters."""
    central = config["central"]
    role_prefix = f"{config['deployment_id']}-replication"
    source_accounts = sorted({s["account_id"] for s in config["sources"]})
    destination = {**central, "kind": "central", "template": "bedrock-central-bucket.yaml",
                   "parameters": {"CentralBucketName": central["bucket_name"],
                                  "SourceAccountIds": ",".join(source_accounts),
                                  "ReplicationRoleNamePrefix": role_prefix,
                                  "EnableKmsEncryption": str(central.get("kms", False)).lower(),
                                  "RetentionDays": str(central.get("retention_days", 0))}}
    sources = [source_unit(source, config, role_prefix) for source in config["sources"]]
    return [destination, *sources]


def source_unit(source: dict, config: dict, role_prefix: str) -> dict:
    """Return one original-bucket stack intent with a central replication destination."""
    central = config["central"]
    partition = region_partition(central["region"])
    if partition is None:
        raise ValueError("central region must belong to a supported AWS partition")
    parameters = {
        "LogBucketName": source["bucket_name"],
        "KeyPrefix": source.get("key_prefix", ""),
        "LoggingMode": "Managed",
        "VantageCrossAccountRole": source.get("vantage_role", ""),
        "ReplicationRoleNamePrefix": role_prefix,
        "ReplicationDestinationBucketArn": f"arn:{partition}:s3:::{central['bucket_name']}",
        "ReplicationDestinationAccountId": central["account_id"],
        "ReplicationDestinationKmsKeyArn": "@central.ReplicationDestinationKmsKeyArn",
        "LogKmsKeyArn": source.get("kms_key_arn", ""),
        "RetainLoggingOnDelete": "true",
        "LogRetentionDays": str(source.get("retention_days", 0)),
    }
    return {**source, "kind": "source", "template": "bedrock-logging.yaml",
            "parameters": parameters}


def logging_conflict(unit: dict, logging_config: dict | None) -> str:
    """Reject taking over preexisting logging during a fresh deployment."""
    if unit["kind"] != "source" or not logging_config:
        return ""
    bucket = (logging_config.get("s3Config") or {}).get("bucketName", "CloudWatch only")
    return (f"Bedrock logging already exists in {unit['account_id']}/{unit['region']} ({bucket}). "
            "Preserve it: update its owning stack or use explicit Reuse mode in the template. "
            "The new-stack wrapper will not take it over.")


def new_manifest(config: dict, template_hashes: dict, observations: list[dict], created_at: str,
                 template_bodies: dict | None = None) -> dict:
    """Return a versioned plan that distinguishes AWS deployment from Vantage verification."""
    units = [{**unit, "status": "planned", "observations": observation}
             for unit, observation in zip(deployment_units(config), observations, strict=True)]
    return {"version": 1, "created_at": created_at, "config": deepcopy(config),
            "config_hash": fingerprint(config), "template_hashes": dict(template_hashes),
            "template_bodies": dict(template_bodies or {}), "units": units,
            "vantage_verified": False,
            "vantage_next_steps": ["Connect original buckets using the existing GA console flow",
                                   "Run Check Permissions with Vantage's actual role",
                                   "Observe Import History and correct account/tag costs"]}


def resolved_parameters(unit: dict, central_outputs: dict) -> list[dict]:
    """Resolve central outputs only after the destination stack succeeds."""
    values = {key: central_outputs[value.removeprefix("@central.")]
              if value.startswith("@central.") else value
              for key, value in unit["parameters"].items()}
    return [{"ParameterKey": key, "ParameterValue": value} for key, value in values.items()]


def original_bucket_handoff(unit: dict) -> dict:
    """Return the original bucket and account scope that current GA Vantage must read."""
    return {"account_id": unit["account_id"], "bucket": unit["bucket_name"],
            "region": unit["region"],
            "prefix": log_prefix(unit["account_id"], unit["region"], unit.get("key_prefix", ""))}


def identity_problem(unit: dict, identity: dict) -> str:
    """Return an account mismatch before the shell accesses deployment resources."""
    if identity.get("Account") == unit["account_id"]:
        return ""
    return (f"AWS profile {unit.get('profile') or '(default)'} is signed into "
            f"{identity.get('Account', 'an unknown account')}; expected {unit['account_id']}. "
            "No deployment was started.")


def initial_stack_problem(unit: dict, stack: dict | None) -> str:
    """Reject every existing stack when creating a fresh deployment plan."""
    if stack is None:
        return ""
    return (f"Stack {unit['stack_name']} already exists in {unit['account_id']}/{unit['region']}. "
            "Use its saved manifest to resume or review an explicit CloudFormation update; "
            "the new-stack wrapper will not adopt it.")


def creation_intent(unit: dict, template_body: str, parameters: list[dict]) -> str:
    """Digest the target and exact create request independently of manifest progress."""
    return fingerprint({"account_id": unit["account_id"], "region": unit["region"],
                        "stack_name": unit["stack_name"], "template_body": template_body,
                        "parameters": sorted(parameters, key=lambda item: item["ParameterKey"])})


def stack_creation_tags(deployment_id: str, intent_hash: str) -> list[dict]:
    """Return ownership and exact-intent markers for interrupted-create recovery."""
    return [{"Key": "bedrock-demo:deployment-id", "Value": deployment_id},
            {"Key": "bedrock-demo:intent-sha256", "Value": intent_hash}]


def stack_resume_problem(unit: dict, stack: dict | None, deployment_id: str,
                         intent_hash: str) -> str:
    """Reject missing, replaced, unowned, or differently configured stacks on resume."""
    name = unit["stack_name"]
    if stack is None:
        return (f"Recorded stack {unit.get('stack_id') or name} no longer exists. "
                "Inspect retained resources before planning a new deployment.")
    if unit.get("stack_id") and stack.get("StackId") != unit["stack_id"]:
        return f"Stack {name} has a different ID from the saved manifest; refusing to resume."
    if stack.get("StackName") != name:
        return f"Stack ID does not identify the planned stack {name}; refusing to resume."
    tags = {tag["Key"]: tag["Value"] for tag in stack.get("Tags", [])}
    if tags.get("bedrock-demo:deployment-id") != deployment_id:
        return f"Stack {name} is not owned by deployment {deployment_id}; refusing to resume."
    if not intent_hash or tags.get("bedrock-demo:intent-sha256") != intent_hash:
        return (f"Stack {name} does not match the planned template and parameters; "
                "refusing to resume.")
    return ""


def stack_snapshot(stack: dict, intent_hash: str) -> dict:
    """Return only serializable deployment progress for the saved manifest."""
    outputs = {output["OutputKey"]: output["OutputValue"] for output in stack.get("Outputs", [])}
    return {"stack_id": stack["StackId"], "status": stack["StackStatus"],
            "intent_hash": intent_hash, "reason": stack.get("StackStatusReason", ""),
            "outputs": outputs}


def missing_stack_response(response: dict) -> bool:
    """Recognize CloudFormation's missing-stack error without hiding other validation errors."""
    error = response.get("Error", {})
    message = error.get("Message", "")
    return (error.get("Code") == "ValidationError" and message.startswith("Stack with id ")
            and message.endswith(" does not exist"))
