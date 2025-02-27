locals {
  # decodes the csv file in the directory
  csv_data = csvdecode(file("projects.csv"))

  # creates a map of lists that lists all projects per owner
  projects_per_owner = {
    for item in local.csv_data :
    item.owner => item.project_account...
  }
}

# uncomment and run `terraform output` to see what these values
# output in the CLI

# output "csv_data" {
#   value = local.csv_data
# }

# output "projects_per_owner" {
#   value = local.projects_per_owner
# }

resource "vantage_virtual_tag_config" "project_virtual_tag_config" {
  key            = "Project Owners"
  backfill_until = "2024-01-01"
  overridable    = false
  values = flatten([
    for owner, projects in local.projects_per_owner : [
      {
        name   = owner
        filter = "costs.provider = 'aws' AND costs.account_id IN (${join(", ", [for project in projects : "'${project}'"])})"
      }
    ]
  ])
}
