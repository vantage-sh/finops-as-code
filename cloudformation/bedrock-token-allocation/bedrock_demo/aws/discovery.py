"""Read Bedrock spend and organization account names without changing AWS."""
from __future__ import annotations

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

GLOBAL_REGION = "us-east-1"  # Cost Explorer and Organizations both live here in commercial AWS


def service_dimension_values(ce: BaseClient, window: dict) -> list[str]:
    """Return every Cost Explorer SERVICE dimension value mentioning Bedrock."""
    response = ce.get_dimension_values(TimePeriod=window, Dimension="SERVICE",
                                       SearchString="Bedrock")
    return [value["Value"] for value in response["DimensionValues"]]


def cost_groups(ce: BaseClient, window: dict, services: list[str]) -> list[dict]:
    """Return the raw GetCostAndUsage periods for the Bedrock services, all pages."""
    results, token = [], None
    while True:
        kwargs = {"NextPageToken": token} if token else {}
        response = ce.get_cost_and_usage(
            TimePeriod=window, Granularity="MONTHLY", Metrics=["UnblendedCost"],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": services}},
            GroupBy=[{"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
                     {"Type": "DIMENSION", "Key": "REGION"}], **kwargs)
        results += response["ResultsByTime"]
        token = response.get("NextPageToken")
        if not token:
            return results


def organization_roster() -> tuple[dict, str | None, str | None, str]:
    """Return ({account_id: name}, org root id, management account id, why the org read failed)."""
    org = boto3.client("organizations", region_name=GLOBAL_REGION)
    management = management_account_id(org)
    try:
        pages = org.get_paginator("list_accounts").paginate()
        names = {account["Id"]: account["Name"]
                 for page in pages for account in page["Accounts"]}
        roots = org.list_roots()["Roots"]
        return names, roots[0]["Id"] if roots else None, management, ""
    except (ClientError, BotoCoreError) as error:
        return {}, None, management, str(error)


def management_account_id(org: BaseClient) -> str | None:
    """Return the organization's management account id, readable from any member account."""
    try:
        return org.describe_organization()["Organization"]["MasterAccountId"]
    except (ClientError, BotoCoreError):
        return None
