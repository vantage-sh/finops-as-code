# AWS Data Transfer Report

Create this report to view data transfer costs for AWS in Vantage.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- AWS as a [connected provider](https://www.vantage.sh/integrations/aws)

## Create the Cost Report

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`). 
2. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
