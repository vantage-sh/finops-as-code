locals {
  team_csv_content = <<-CSV
    teams
    integrations
    security
    ingestion
    analytics
    core
  CSV

  all_teams = csvdecode(local.team_csv_content)
}

resource "vantage_virtual_tag_config" "team_tag" {
  key            = "team_virtual_tag"
  backfill_until = "2024-01-01"
  overridable    = false

  values = [
    for t in local.all_teams : {
      name   = t.teams
      filter = "(costs.provider = 'aws' AND (tags.name = 'team' AND tags.value = '${t.teams}')) OR (costs.provider = 'kubernetes' AND (tags.name = 'organization/team' AND tags.value = '${t.teams}'))"
    }
  ]
}
