output "created_saved_filter" {
  value = vantage_saved_filter.filter.token
}

output "marketing_aws_cost_report_token" {
  value = vantage_cost_report.report.token
}

output "marketing_snowflake_cost_report_token" {
  value = vantage_cost_report.report.token
}