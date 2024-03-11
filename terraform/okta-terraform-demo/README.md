# Using Terraform to Automate Okta SSO Group Access

Your organization just started using Vantage. As the Okta administrator, you have a set of existing Okta groups with users that will need to access Vantage. You want to use Terraform and have these user groups in Okta be reflected in Vantage, with the same group members. You have a CSV file that contains the list of groups you need to manage.

In this demo, we’ll complete the following steps:

- Set up an SSO connection between Okta and Vantage that allows for SSO group mapping
- With the Vantage and Okta Terraform providers:
  - Assign the Vantage app to specific Okta groups
  - Create teams in Vantage that have the same names as the Okta groups
  - Create a set of Vantage Cost Reports and folders with specific access grants tied to each team

## Prerequisites

See the necessary prerequisites in the corresponding [demo blog](https://www.vantage.sh/blog/okta-terraform#prerequisites).

## Reference

- [Vantage blog](https://www.vantage.sh/blog/okta-terraform)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Okta Terraform provider](https://registry.terraform.io/providers/okta/okta/latest/docs)
