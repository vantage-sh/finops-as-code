"""Thin AWS shell for creating or reusing Bedrock logging safely."""
from __future__ import annotations

from bedrock_demo.core.lifecycle import logging_change, needs_logging_read


def handler(event: dict, context: object) -> None:
    """Apply the ownership-checked operation and answer CloudFormation."""
    import boto3
    import cfnresponse

    properties = event.get("ResourceProperties", {})
    physical_id = event.get("PhysicalResourceId", "")
    fallback_id = physical_id or "bedrock-mil-unowned"
    try:
        if not needs_logging_read(event["RequestType"], properties, physical_id, event["StackId"]):
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, fallback_id)
            return
        client = boto3.client("bedrock")
        current = client.get_model_invocation_logging_configuration().get("loggingConfig")
        change = logging_change(event["RequestType"], current, properties,
                                event.get("OldResourceProperties") or {}, physical_id,
                                event["StackId"])
        if change["action"] == "put":
            client.put_model_invocation_logging_configuration(loggingConfig=change["configuration"])
        if change["action"] == "delete":
            client.delete_model_invocation_logging_configuration()
        cfnresponse.send(event, context, cfnresponse.SUCCESS,
                         {"Bucket": properties["BucketName"], "Applied": change["action"]},
                         change["physical_id"])
    except Exception as error:
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, fallback_id,
                         reason=str(error)[:900])
