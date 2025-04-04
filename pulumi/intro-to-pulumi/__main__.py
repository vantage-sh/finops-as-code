"""A Python Pulumi program"""

import pulumi
import pulumi_vantage as vantage
config = pulumi.Config()
workspace_token = config.require_secret("workspace_token")

report_structure = [
    {
        "provider": "aws",
        "folder_title": "AWS Folder",
        "filter_title": "AWS Saved Filter",
        "report_title": "AWS Cost Report",
    },
    {
        "provider": "snowflake",
        "folder_title": "Snowflake Folder",
        "filter_title": "Snowflake Saved Filter",
        "report_title": "Snowflake Cost Report",
    },
]

def create_cost_structure(provider, folder_title, workspace_token, filter_title, report_title):
    folder = vantage.Folder("{}Folder".format(provider),
        title=folder_title,
        workspace_token=workspace_token)
    saved_filter = vantage.SavedFilter("{}Filter".format(provider),
        workspace_token=workspace_token,
        filter="(costs.provider = '{}')".format(provider),
        title=filter_title)
    report = vantage.CostReport("{}Report".format(provider),
        folder_token=folder.token,
        saved_filter_tokens=[saved_filter.token],
        title=report_title,
        chart_type="bar",
        date_bin="month")

    return folder, saved_filter, report

reports = []

for report_info in report_structure:
    provider = report_info["provider"]
    folder, saved_filter, report = create_cost_structure(
        provider,
        report_info["folder_title"],
        workspace_token,
        report_info["filter_title"],
        report_info["report_title"]
    )

    reports.append(report.token)

marketing_dashboard = vantage.Dashboard("marketingDashboard",
    workspace_token=workspace_token,
    date_interval="last_6_months",
    title="Marketing Dashboard",
    widgets=[{
        "settings": { "display_type": "chart" },
        "widgetable_token": token
    } for token in reports])
