# vantage-stack.py
from constructs import Construct
from imports.vantage.cost_report import CostReport
from imports.vantage.folder import Folder
from imports.vantage.saved_filter import SavedFilter

class VantageCostStack(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        folder_title: str,
        filter_title: str,
        cost_report_title: str, 
        filter_expression: str,
        workspace_token: str
    ):
        super().__init__(scope, id)

        vantage_folder = Folder(
            self,
            "vantage_folder",
            title=folder_title,
            workspace_token=workspace_token
        )

        saved_filter = SavedFilter(
            self,
            "vantage_filter",
            title=filter_title,
            filter=filter_expression,
            workspace_token=workspace_token
        )

        cost_report = CostReport(
            self,
            "vantage_cost_report",
            title=cost_report_title,
            folder_token=vantage_folder.token,
            saved_filter_tokens=[saved_filter.token],
            workspace_token=workspace_token
        )