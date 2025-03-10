locals {
  # decodes the csv file in the directory
  csv_data = csvdecode(file("teams.csv"))

  # creates a map of lists that lists all namespace per team
  namespaces_per_team = {
    for item in local.csv_data :
    item.team => item.namespace...
  }
}

# uncomment and run `terraform output` to see what these values
# output in the CLI

# output "csv_data" {
#   value = local.csv_data
# }

# output "namespaces_per_team" {
#   value = local.namespaces_per_team
# }

resource "vantage_virtual_tag_config" "project_virtual_tag_config" {
  key            = "Temporal Cloud Namespaces"
  backfill_until = "20245-03-01"
  overridable    = false
  values = flatten([
    for team, namespaces in local.namespaces_per_team : [
      {
        name   = team
        filter = "costs.provider = 'temporal' AND (costs.service = 'Temporal Cloud' AND costs.resource_id IN (${join(", ", [for namespace in namespaces : "'${namespace}'"])})"
      }
    ]
  ])
}
