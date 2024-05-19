resource "vantage_cost_report" "s3_report" {
  title               = "S3 Report"
  filter = <<-FILTER
    (costs.provider = 'aws' AND costs.service = 'Amazon Simple Storage Service') AND
    (costs.provider = 'aws' AND (costs.service = 'Amazon Simple Storage Service' AND costs.category = 'API Request'))
    FILTER
  groupings = "region,resource_id"
  workspace_token = var.workspace_token
}
