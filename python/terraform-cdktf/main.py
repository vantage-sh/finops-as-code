import os
from constructs import Construct
from cdktf import App, TerraformStack
from imports.vantage.provider import VantageProvider
from vantage-stack import VantageCostStack


class MyStack(TerraformStack):
    def __init__(self, scope: Construct, id: str):
        super().__init__(scope, id)

        VantageProvider(
            self,
            "vantage",
            api_token=os.environ["VANTAGE_API_TOKEN"]
        )

        VantageCostStack(
        self,
        "aws_cost_stack",
        folder_title="AWS Costs",
        filter_title="AWS Filter",
        cost_report_title="AWS Report",
        filter_expression="costs.provider = 'aws'",
        workspace_token=os.environ["VANTAGE_WORKSPACE_TOKEN"]
        )

        VantageCostStack(
        self,
        "snowflake_cost_stack",
        folder_title="Snowflake Costs",
        filter_title="Snowflake Filter",
        cost_report_title="Snowflake Report",
        filter_expression="costs.provider = 'snowflake'",
        workspace_token=os.environ["VANTAGE_WORKSPACE_TOKEN"]
        )


app = App()
MyStack(app, "vantage_cdktf_example")

app.synth()