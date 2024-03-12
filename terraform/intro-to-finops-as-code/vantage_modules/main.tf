resource "vantage_folder" "folder" {
  title           = var.folder_title
  workspace_token = var.workspace_token
}

resource "vantage_saved_filter" "filter" {
  title           = "${var.folder_title} Filter"
  filter = <<FILTER
    (costs.provider  = '${var.service}'
    AND tags.name    = '${var.tag_name}'
    AND tags.value   = '${var.tag_value}')
FILTER
  workspace_token = var.workspace_token
}

resource "vantage_cost_report" "report" {
  title               = "${var.folder_title} Report"
  folder_token        = vantage_folder.folder.token
  saved_filter_tokens = [vantage_saved_filter.filter.token]
  workspace_token     = var.workspace_token
}