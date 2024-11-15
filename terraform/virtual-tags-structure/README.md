# Using Terraform to Build a Virtual Tagging Structure

A virtual tag is a way to consistently tag your costs across providers in Vantage. Virtual tags can help you increase tagging coverage across your cloud infrastructure. Create cost allocation tag keys with a set of corresponding values and filters directly in the Vantage without needing to involve your engineering team in making infrastructure changes.

## Scenario

Your organization wants to start tracking cloud resource usage based on different projects. Projects are associated with different AWS accounts, and each account has an associated project owner. You have a list of all account names and their associated owner. Each owner can have one or many associated projects/accounts. In this demo, you'll use the `projects.csv` file to create a virtual tag that tracks these costs. With this file, you'll:

- Create a single virtual tag.
- The tag will have custom values that are related to each project owner.
- Each tag value will include a filter for specific AWS accounts that the owner is responsible for.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create the Virtual Tag

The script first reads the CSV file from the current directory with the `csv_data` local variable. The resulting data structure is a list of maps. For example:

```bash
local.csv_data = [
  { Owner = "Rajan Gohil", Account = "account-1" },
  { Owner = "Rajan Gohil", Account = "account-2" },
  { Owner = "Rajan Gohil", Account = "account-3" },
  # continues
]
```

Another local variable, `projects_per_owner`, unpacks the CSV file to take each project owner and make them a key with a list of accounts as the value:

```bash
projects_per_owner = {
  "Rajan Gohil" = ["account-1", "account-2", "account-3"]
  "Tara Finn" = ["account-4", "account-5", "account-6"]
  "Meagan Jones" = ["account-7", "account-8", "account-9"]
}
```

> **Tip:** The script also provides outputs for each of these variables so that you can view their structure.

The `vantage_virtual_tag_config` [resource](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs/resources/virtual_tag_config) creates the virtual tag with a name of `Project Owners`. The `backfill_untl` and `overridable` parameters define the earliest date for which the tag should apply and if the tag should override any existing provider tags with the same values.

```bash
resource "vantage_virtual_tag_config" "project_virtual_tag_config" {
  key            = "Project Owners"
  backfill_until = "2024-01-01"
  overridable    = false
  ...
```

The `values` block uses the `flatten` [function](https://developer.hashicorp.com/packer/docs/templates/hcl_templates/functions/collection/flatten) to transform a list of lists into a single flat list. Each list generated within the `for` expression corresponds to a project owner and their associated accounts.

```bash
  ...
  values = flatten([
    for owner, projects in local.projects_per_owner : [
      {
        name   = owner
        filter = "costs.provider = 'aws' AND costs.account_id IN (${join(", ", [for project in projects : "'${project}'"])})"
      }
    ]
  ])
}
```

The `filter` uses Vantage Query Language (see **Reference** section below) to construct an expression that selects all associated accounts associated with the specific project owner. For example, the expression for one owner will evaluate to:

```bash
costs.provider = 'aws' AND costs.account_id IN ('account-1', 'account-2', 'account-3')
```

Deploy this configuration with `terraform plan` and `terraform apply`. The virtual tag should be immediately available in Vantage for use in reports.

## Reference

- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Virtual Tagging](https://docs.vantage.sh/virtual_tagging) documentation
- [Vantage Query Language](https://docs.vantage.sh/vql)
