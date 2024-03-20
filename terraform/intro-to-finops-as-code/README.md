# Intro to FinOps as Code with Terraform

This demo is an introduction to FinOps as Code on Vantage. In this demo, we'll set up a basic Terraform deployment to create two Cost Reports, a set of folders, and a dashboard.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create Vantage Resources

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`).
2. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage blog](https://www.vantage.sh/blog/finops-as-code-with-terraform)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
