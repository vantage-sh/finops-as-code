# Using Terraform to Build a Cost Allocation Segment Structure

A segment is a set of filters that represents a portion of costs for your organization (e.g., costs allocated to a business unit or team). With segments, you can perform cost allocation and enforce cost governance for your organization. You can create nested hierarchies of costs that can map to teams, departments, apps, or services within your organization. Segments ensure that costs are allocated only once and not duplicated in cases of showback/chargeback scenarios.

The below diagram shows an example of a segment hierarchy. All child and grandchild segment costs roll up to the top-level organization segment. Any costs not assigned to a segment are considered unallocated costs. By analyzing your segments, you can identify and burn down these unallocated costs to improve financial accountability and resource management.

<img src="https://docs.vantage.sh/img/segment-tree.png" alt="Tree diagram of segments with an Organization at the top, three child business unit segments, and two grandchild segments per child segment that represent teams. Each child and grandchild segment has an arrow that points up to the organization segment at the top." width="500" height="auto">

In this demo, your organization uses a structure that's defined in the included `cost-centers.yaml` file. With this file, you'll:

- Create an organization-level parent segment that represents the whole organization.
- Create a set of first-level child segments for each business unit.
- Create a set of second-level child segments for each team.
  - Each team segment has a filter that maps to a corresponding cost center.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

## Create the Segment Hierarchy

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`). 
2. The `filter` on the team-level child segments assumes the organization uses GCP as its main cloud provider and has `cost_center` labels attached to resources in its cloud environment. You can update this `filter` as needed. See the **Reference** section below.
3. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Cost allocation segments](https://docs.vantage.sh/segments) documentation
- [Vantage Query Language](https://docs.vantage.sh/vql)
