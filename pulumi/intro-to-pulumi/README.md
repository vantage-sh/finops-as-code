# Intro to FinOps as Code with Pulumi

This demo is an introduction to FinOps as Code on Vantage. In this demo, we'll set up a basic Pulumi deployment to create two Cost Reports, a set of folders, and a dashboard.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- Export the Vantage API host with: `export VANTAGE_API_HOST="https://api.vantage.sh"`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create Vantage Resources

1. Generate the Vantage provider as a local package:
  ```bash
  pulumi package add terraform-provider vantage-sh/vantage
  ```
2. Configure your Vantage workspace token as a Pulumi Secret:
  ```bash
  pulumi login
  pulumi stack select vantage
  pulumi config set --secret workspace_token <WORKSPACE_TOKEN>
  ```
3. Deploy this configuration with `pulumi up`.

## Reference

- [Vantage blog](https://www.vantage.sh/blog/pulumi-vs-terraform)
- [Vantage Pulumi provider](https://www.pulumi.com/registry/packages/vantage/)
- [Vantage Query Language](https://docs.vantage.sh/vql)
