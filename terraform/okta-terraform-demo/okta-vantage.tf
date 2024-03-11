locals {
  okta_groups = csvdecode(file("okta-groups.csv"))
}

data "okta_group" "group_info" {
  for_each = { for k, group in local.okta_groups : k => group }
  name     = each.value.name
}

data "okta_app" "app_info" {
  label = "Vantage"
}

resource "okta_app_group_assignments" "vantage_app" {
  app_id = data.okta_app.app_info.id

  dynamic "group" {
    for_each = data.okta_group.group_info
    content {
      id = group.value.id
    }
  }
}

resource "vantage_folder" "group_folders" {
  for_each        = { for group in local.okta_groups : group.name => group }
  title           = each.value.name
  workspace_token = var.vantage_workspace_token
}

resource "vantage_cost_report" "group_reports" {
  for_each     = { for group in local.okta_groups : group.name => group }
  folder_token = vantage_folder.group_folders[each.key].token
  filter       = "costs.provider = 'aws' AND (tags.name, tags.value) IN (('team', '${lower(each.value.name)}'))"
  title        = "${each.value.name} Costs"
}

resource "vantage_team" "okta_team" {
  for_each    = { for group in local.okta_groups : group.name => group }
  name        = each.value.name
  description = "Team automatically created from Okta group ${each.value.name}"
}

resource "vantage_access_grant" "okta_team_access_grant" {
  for_each       = { for team_name, team in vantage_team.okta_team : team_name => team }
  team_token     = each.value.token
  resource_token = vantage_folder.group_folders[each.key].token
  access         = "allowed"
}

data "vantage_teams" "teams_info" {

}

locals {
  everyone_team_token = {
    for team in data.vantage_teams.teams_info.teams :
    team.name => team.token
    if team.name == "Everyone"
  }

  folder_tokens = { for key, folder in vantage_folder.group_folders : key => folder.token }
}

resource "vantage_access_grant" "okta_team_deny_grant" {
  for_each       = local.folder_tokens
  team_token     = local.everyone_team_token["Everyone"]
  resource_token = each.value
  access         = "denied"
}
