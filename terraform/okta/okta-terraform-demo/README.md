# Using Terraform to Automate Okta SSO Group Access

Your organization just started using Vantage. As the Okta administrator, you have a set of existing Okta groups with users that will need to access Vantage. You want to use Terraform and have these user groups in Okta be reflected in Vantage, with the same group members. You have a CSV file that contains the list of groups you need to manage.

In this demo, we’ll complete the following steps:

- Set up an SSO connection between Okta and Vantage that allows for SSO group mapping
- With the Vantage and Okta Terraform providers:
  - Assign the Vantage app to specific Okta groups
  - Create teams in Vantage that have the same names as the Okta groups
  - Create a set of Vantage Cost Reports and folders with specific access grants tied to each team

<img src="/assets/okta-terraform.png" alt="A diagram that starts with a CSV icon. CSV points to the Terraform logo. The Terraform logo has one arrow that points to the Okta logo and one that points to the Vantage logo. Under the Okta logo are three squares that say Assign App to Groups. Under the Vantage logo is one set of three squares that says Vantage Resources. Another square says Teams and Access Grants and has three user icons with checkmarks over them." width="500" height="auto">

## Prerequisites

### Okta

You will need to be an Okta administrator for your organization with the ability to assign applications to groups and create a SAML SSO application. You will also need access to API credentials to create a connection with Terraform. See the [Okta documentation](https://help.okta.com/en-us/content/topics/security/administrators-admin-comparison.htm) for details on administrator permissions. Ensure you have a valid [Okta API token](https://developer.okta.com/docs/guides/create-an-api-token/main/).

### Vantage

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)

### Okta SAML Connection in Vantage

See the [demo blog](https://www.vantage.sh/blog/okta-terraform#create-a-saml-sso-connection-between-okta-and-vantage) for more information on how to set up an Okta SAML SSO connection in Vantage. 

## Reference

- [Vantage blog](https://www.vantage.sh/blog/okta-terraform)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Okta Terraform provider](https://registry.terraform.io/providers/okta/okta/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
