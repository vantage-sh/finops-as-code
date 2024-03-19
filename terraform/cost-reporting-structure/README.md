# Using Terraform to Build a Cost Reporting Structure

Effective cost management is critical for organizations to optimize their cloud spending and align it with business objectives. FinOps as Code uses Infrastructure as Code principles to re-create your business structure in a third-party cost optimization tool, like Vantage, so you can visualize your organization’s structure alongside accrued costs. 

In this demo, your organization uses a structure that's defined in the included `cost-centers.yaml` file. With this file, you'll:

- Create a set of folders in Vantage for each business unit.
- Create a set of Cost Reports for each team.
  - Your company tags resources based on a cost_center tag. Each team’s Cost Report will be filtered by its corresponding cost_center tag to include only costs attributed to that team/cost center.
- Create a dashboard for each business unit that contains the Cost Reports for its associated teams.

<img src="/assets/terraform-cost-reporting.png" alt="A diagram that starts with a YAML icon. YAML points to the Terraform logo. The Terraform logo has one arrow that points to the Vantage logo, which is in a box. Under the Vantage logo is an arrow that points to one set of three folder icons that say Business Unit Folders. Another arrow points to three report icons that say Team Cost/Center Cost Reports. A third arrow points to three dashboard icons that say Business Unit Dashboards." width="500" height="auto">

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create the Organization Structure

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`). 
2. The `filter` on the `vantage_cost_report` assumes the organization uses GCP as its main cloud provider and has `cost_center` labels attached to resources in their cloud environment. You can update this `filter` as needed. See the **Reference** section below.
3. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage blog](https://www.vantage.sh/blog/terraform-cost-reports)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
