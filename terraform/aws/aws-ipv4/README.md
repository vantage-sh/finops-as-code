# AWS IPv4 Report

As of February 2024, AWS charges for in-use AWS Public IPv4 addresses. Create a Cost Report to track your AWS Public IPv4 total costs and forecasted costs in Vantage.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- AWS as a [connected provider](https://www.vantage.sh/integrations/aws)

## Create the Cost Report

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`). 
2. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage blog](https://www.vantage.sh/blog/aws-public-ipv4-cost-and-how-to-see)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
