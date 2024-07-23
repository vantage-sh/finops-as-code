# Using Terraform to Automate Cost Allocation Tags

You currently tag AWS and Kubernetes resources with tags that identify owners by team. To more easily show back each team's share of costs in reporting, you decide to create a group of virtual tags, in Vantage, that combine the AWS costs and Kubernetes costs into one value for each team. You will use the Vantage Terraform provider to easily automate this process for hundreds of team tag groups. With the Terraform provider, you can iterate through a list of your existing tag names and create new cost tags.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create the Teams Virtual Tag

1. The `local` variables in `main.tf` use sample data. Update these variables to match your use case.
2. The `filter` item in the virtual tag resource uses Vantage Query Language. See the Reference section below and update this filter for your use case.
3. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Virtual Tags](https://docs.vantage.sh/virtual_tagging) documentation
- [Vantage Query Language](https://docs.vantage.sh/vql)
