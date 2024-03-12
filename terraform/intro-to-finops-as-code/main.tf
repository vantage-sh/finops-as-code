module "marketing_aws" {
  source          = "./vantage_modules"
  folder_title    = "Marketing AWS Costs"
  workspace_token = var.marketing_workspace_token
  service         = "aws"
  tag_name        = "cost_center"
  tag_value       = "marketing"
}

module "marketing_snowflake" {
  source          = "./vantage_modules"
  folder_title    = "Marketing Snowflake Costs"
  workspace_token = var.marketing_workspace_token
  service         = "snowflake"
  tag_name        = "cost_center"
  tag_value       = "marketing"
}

resource "vantage_dashboard" "dashboard" {
  widget_tokens = [
    module.marketing_aws.marketing_aws_cost_report_token,
    module.marketing_snowflake.marketing_snowflake_cost_report_token
  ]
  title           = "Marketing Dashboard"
  date_interval   = "last_6_months"
  date_bin        = "month"
  workspace_token = var.marketing_workspace_token
}


