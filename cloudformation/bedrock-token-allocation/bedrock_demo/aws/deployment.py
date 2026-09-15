"""Create only reviewed CloudFormation stacks and resume their observed progress."""
from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from bedrock_demo.core.deployment import (
    creation_intent,
    fingerprint,
    identity_problem,
    initial_stack_problem,
    logging_conflict,
    missing_stack_response,
    stack_creation_tags,
    stack_resume_problem,
    stack_snapshot,
)

if TYPE_CHECKING:
    from boto3.session import Session
    from botocore.client import BaseClient

RETRYABLE_CREATE_ERRORS = ("AlreadyExistsException", "TokenAlreadyExistsException")


def checked_session(unit: dict, session: Session | None = None) -> tuple[Session, dict]:
    """Resolve the configured AWS profile and verify its account before other AWS calls."""
    active = session or boto3.session.Session(profile_name=unit.get("profile") or None,
                                             region_name=unit["region"])
    identity = active.client("sts", region_name=unit["region"]).get_caller_identity()
    problem = identity_problem(unit, identity)
    if problem:
        raise ValueError(problem)
    return active, identity


def find_stack(client: BaseClient, stack_name: str) -> dict | None:
    """Describe one exact stack, treating only the specific missing-stack response as absent."""
    try:
        return client.describe_stacks(StackName=stack_name)["Stacks"][0]
    except ClientError as error:
        if missing_stack_response(error.response):
            return None
        raise


def inspect_unit(unit: dict, deployment_id: str, template_body: str = "", *,
                 session: Session | None = None) -> dict:
    """Read target identity, stack absence, and logging ownership before saving a new plan."""
    active, identity = checked_session(unit, session)
    client = active.client("cloudformation", region_name=unit["region"])
    existing = find_stack(client, unit["stack_name"])
    problem = initial_stack_problem(unit, existing)
    if problem:
        raise ValueError(problem)
    config = inspect_logging(active, unit)
    if template_body:
        client.validate_template(TemplateBody=template_body)
    return {"account_id": identity["Account"], "caller_arn": identity.get("Arn", ""),
            "deployment_id": deployment_id, "stack_exists": False, "logging_config": config,
            "template_validated": bool(template_body)}


def inspect_logging(session: Session, unit: dict) -> dict | None:
    """Read source logging and reject an existing configuration before a fresh create."""
    if unit["kind"] != "source":
        return None
    bedrock = session.client("bedrock", region_name=unit["region"])
    config = bedrock.get_model_invocation_logging_configuration().get("loggingConfig")
    problem = logging_conflict(unit, config)
    if problem:
        raise ValueError(problem)
    return config


def owned_snapshot(unit: dict, stack: dict | None, deployment_id: str, intent_hash: str) -> dict:
    """Apply the pure ownership guard before returning resumable stack progress."""
    problem = stack_resume_problem(unit, stack, deployment_id, intent_hash)
    if problem:
        raise ValueError(problem)
    assert stack is not None
    return stack_snapshot(stack, intent_hash)


def start_or_resume_stack(unit: dict, deployment_id: str, template_body: str,
                          parameters: list[dict], *, session: Session | None = None) -> dict:
    """Create a new stack once or recover an existing stack with the same tagged intent."""
    active, _ = checked_session(unit, session)
    client = active.client("cloudformation", region_name=unit["region"])
    intent_hash = creation_intent(unit, template_body, parameters)
    existing = find_stack(client, unit.get("stack_id") or unit["stack_name"])
    if existing is not None or unit.get("stack_id"):
        return owned_snapshot(unit, existing, deployment_id, intent_hash)
    inspect_logging(active, unit)
    token = f"bedrock-{fingerprint({'deployment_id': deployment_id, 'intent_hash': intent_hash})}"
    try:
        result = client.create_stack(
            StackName=unit["stack_name"], TemplateBody=template_body, Parameters=parameters,
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Tags=stack_creation_tags(deployment_id, intent_hash), ClientRequestToken=token,
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in RETRYABLE_CREATE_ERRORS:
            raise
        existing = find_stack(client, unit["stack_name"])
        if existing is None:
            raise
        return owned_snapshot(unit, existing, deployment_id, intent_hash)
    return {"stack_id": result["StackId"], "status": "CREATE_IN_PROGRESS",
            "intent_hash": intent_hash, "outputs": {}, "reason": "", "request_token": token}


def describe_owned_stack(unit: dict, deployment_id: str, *,
                         session: Session | None = None) -> dict:
    """Refresh one manifest stack while rechecking its account, ownership, and exact intent."""
    active, _ = checked_session(unit, session)
    client = active.client("cloudformation", region_name=unit["region"])
    stack = find_stack(client, unit.get("stack_id") or unit["stack_name"])
    return owned_snapshot(unit, stack, deployment_id, unit.get("intent_hash", ""))
