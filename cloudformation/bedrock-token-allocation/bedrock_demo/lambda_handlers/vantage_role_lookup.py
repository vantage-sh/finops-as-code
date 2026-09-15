"""Thin AWS shell for resolving the source account's active Vantage role."""
from __future__ import annotations

from bedrock_demo.core.lifecycle import one_vantage_role

PHYSICAL_ID = "bedrock-vantage-role"


def handler(event: dict, context: object) -> None:
    """Resolve one role and answer CloudFormation without changing IAM."""
    import boto3
    import cfnresponse

    try:
        if event["RequestType"] == "Delete":
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, PHYSICAL_ID)
            return
        pages = boto3.client("iam").get_paginator("list_roles").paginate()
        name = one_vantage_role([role["RoleName"] for page in pages for role in page["Roles"]])
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {"RoleNames": name}, PHYSICAL_ID)
    except Exception as error:
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, PHYSICAL_ID,
                         reason=str(error)[:900])
