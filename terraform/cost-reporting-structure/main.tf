locals {
  cost_centers   = yamldecode(file("cost-centers.yaml")).cost_centers
  business_units = toset([for k, cost_center in local.cost_centers : cost_center.business_unit])
}

resource "vantage_folder" "bu_folders" {
  for_each        = local.business_units
  title           = "${each.value} Folder"
  workspace_token = var.workspace_token
}

resource "vantage_cost_report" "team_reports" {
  for_each     = local.cost_centers
  title        = "${each.value.team} Cost Report"
  folder_token = vantage_folder.bu_folders[each.value.business_unit].token
  filter       = "costs.provider = 'gcp' AND (tags.name, tags.value) IN (('cost_center', '${each.key}'))"
}

resource "vantage_dashboard" "bu_dashboard" {
  for_each        = local.business_units
  widget_tokens   = [
    for cost_center_key, cost_center_info in local.cost_centers :
    vantage_cost_report.team_reports[cost_center_key].token
    if cost_center_info.business_unit == each.value
  ]
  title           = "${each.value} Dashboard"
  date_interval   = "last_6_months"
  date_bin        = "week"
  workspace_token = var.workspace_token
}