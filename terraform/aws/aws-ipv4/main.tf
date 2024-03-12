resource "vantage_cost_report" "ipv4_report" {
  title           = "IPv4 Report"
  filter          = <<FILTER
    (costs.provider = 'aws' AND
    (costs.service = 'Amazon Virtual Private Cloud' AND costs.category = 'Other') AND
    (costs.service = 'Amazon Virtual Private Cloud' AND costs.subcategory LIKE '%PublicIPv4%'))
FILTER
  workspace_token = var.workspace_token

}
