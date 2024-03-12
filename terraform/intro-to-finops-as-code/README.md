# Intro to FinOps as Code with Terraform

This demo walks through several FinOps use cases, showcasing how Terraform and other FinOps as Code tools can automate and optimize cloud financial operations. We’ll provide code samples and recommendations for how to get up and running with your FinOps as Code practice.

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
