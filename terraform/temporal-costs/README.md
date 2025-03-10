# Using Terraform to Create Temporal Cloud Namespace Tags

If your teams are running workloads across Temporal Cloud and other infrastructure providers, you can use [Virtual Tags](https://docs.vantage.sh/tagging/) in Vantage to group and analyze total application costs. This example shows you how to create a configuration based on Temporal Cloud namespaces associated with teams.

## Prerequisites

- Valid Read/Write Vantage API token
- Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- Temporal Cloud as a connected provider

## Create the Temporal Cloud Teams–Namespace Virtual Tag

1. The local variables in `main.tf` use sample data. Update these variables to match your use case.
2. The `filter` item in the virtual tag resource uses Vantage Query Language. See the Reference section below and update this filter for your use case.
3. Deploy this configuration with `terraform apply`.
