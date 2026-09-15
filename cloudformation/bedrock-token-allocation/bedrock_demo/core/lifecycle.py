"""Pure ownership and configuration decisions for the logging custom resource."""
from __future__ import annotations

import hashlib

CONFLICT = ("Bedrock logging already exists. This stack will not overwrite it. Use "
            "ExistingLogBucket with LoggingMode=Reuse, preserving its prefix and CloudWatch "
            "configuration.")
REUSE_MISMATCH = ("Reuse requires existing Bedrock S3 logging at this exact bucket and prefix; "
                  "configure it in its owning IaC first.")


def logging_destination(config: dict | None) -> tuple[str | None, str]:
    """Return the S3 bucket and normalized prefix in a logging configuration."""
    s3 = (config or {}).get("s3Config") or {}
    return s3.get("bucketName"), s3.get("keyPrefix", "").strip("/")


def managed_logging_config(bucket: str, prefix: str) -> dict:
    """Return the S3 configuration enabling every supported data-delivery type."""
    s3 = {"bucketName": bucket, **({"keyPrefix": prefix} if prefix else {})}
    return {"s3Config": s3, "textDataDeliveryEnabled": True,
            "imageDataDeliveryEnabled": True, "embeddingDataDeliveryEnabled": True,
            "videoDataDeliveryEnabled": True, "audioDataDeliveryEnabled": True}


def versioned_managed_config(properties: dict) -> dict:
    """Resolve the declared schema while preserving pre-audio resource event behavior."""
    wanted = managed_logging_config(properties["BucketName"], properties.get("KeyPrefix", ""))
    version = str(properties.get("LoggingConfigurationVersion", "1"))
    if version == "2":
        return wanted
    if version == "1":
        return {key: value for key, value in wanted.items() if key != "audioDataDeliveryEnabled"}
    raise ValueError("LoggingConfigurationVersion must be 1 or 2.")


def stack_digest(stack_id: str) -> str:
    """Return the short stable digest that ties a physical ID to its creating stack."""
    return hashlib.sha256(stack_id.encode()).hexdigest()[:32]


def owned_resource_id(stack_id: str) -> str:
    """Return a stable ownership marker tied to the creating CloudFormation stack."""
    return f"bedrock-mil-managed-{stack_digest(stack_id)}"


def config_matches_managed(current: dict | None, wanted: dict) -> bool:
    """Return whether the configuration has only the settings this stack manages."""
    actual = dict(current or {})
    if "audioDataDeliveryEnabled" not in wanted and actual.get("audioDataDeliveryEnabled") is False:
        actual.pop("audioDataDeliveryEnabled")
    if logging_destination(actual) != logging_destination(wanted):
        return False
    actual["s3Config"] = wanted["s3Config"]
    return actual == wanted


def retain_on_delete(properties: dict) -> bool:
    """Return whether stack removal must leave the logging configuration in place."""
    return str(properties.get("RetainLoggingOnDelete", "true")).lower() != "false"


def needs_logging_read(request_type: str, properties: dict, physical_id: str,
                       stack_id: str) -> bool:
    """Return whether this event can need the current logging configuration."""
    if request_type != "Delete":
        return True
    return (not retain_on_delete(properties)
            and properties.get("LoggingMode", "Managed") == "Managed"
            and physical_id == owned_resource_id(stack_id))


def logging_change(request_type: str, current: dict | None, properties: dict,
                   old_properties: dict, physical_id: str, stack_id: str) -> dict:
    """Return the safe action and ownership marker without changing any input."""
    bucket, prefix = properties["BucketName"], properties.get("KeyPrefix", "")
    wanted = versioned_managed_config(properties)
    if request_type not in {"Create", "Update", "Delete"}:
        raise ValueError("Unknown CloudFormation request type.")
    mode = properties.get("LoggingMode", "Managed")
    owned = physical_id == owned_resource_id(stack_id)
    retained_id = physical_id or f"bedrock-mil-reused-{stack_digest(stack_id)}"
    result = {"action": "noop", "physical_id": retained_id, "configuration": wanted}
    if request_type == "Delete":
        deletable = owned and mode == "Managed" and config_matches_managed(current, wanted)
        if not retain_on_delete(properties) and deletable:
            return {**result, "action": "delete"}
        return result
    if mode == "Reuse":
        if logging_destination(current) != (bucket, prefix.strip("/")):
            raise ValueError(REUSE_MISMATCH)
        return result
    if mode != "Managed":
        raise ValueError("LoggingMode must be Managed or Reuse.")
    if not current:
        return {**result, "action": "put", "physical_id": owned_resource_id(stack_id)}
    bucket_owned = str(properties.get("OwnsLogBucket", "false")).lower() == "true"
    if request_type == "Create" and bucket_owned and config_matches_managed(current, wanted):
        return {**result, "physical_id": owned_resource_id(stack_id)}
    if request_type == "Update" and config_matches_managed(current, wanted):
        return result
    old_wanted = versioned_managed_config({"BucketName": bucket, **old_properties})
    if owned and config_matches_managed(current, old_wanted):
        return {**result, "action": "put"}
    raise ValueError(CONFLICT)


def one_vantage_role(role_names: list[str]) -> str:
    """Return one matching Vantage role or explain how to resolve ambiguous discovery."""
    matches = sorted(name for name in role_names
                     if name.startswith(("ConnectToVantage", "StackSet-ConnectToVantage"))
                     and "-CrossAccountRole-" in name)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("No ConnectToVantage role found. Connect this source account to Vantage "
                         "or set VantageCrossAccountRole explicitly.")
    raise ValueError(f"Several Vantage roles found: {', '.join(matches)}. Set "
                     "VantageCrossAccountRole to the active integration role.")
