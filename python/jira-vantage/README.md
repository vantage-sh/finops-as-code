# Automating Jira Issues

Your organization uses Jira to track issues and create tasks for development teams. You also use Vantage to manage your cloud costs. Vantage monitors your connected providers and shows cost recommendations as your infrastructure evolves and changes. You can implement these recommendations to lower your bill. An example Vantage recommendation might look like:

> _We found $319.00 in on demand spend last month. You can contact your Datadog account manager to commit to guaranteed spend and save around 20%._

You want to create Jira issues based on these recommendations so that the teams responsible for affected accounts or cost resources can work to implement these recommendations. The workflow for this demo follows the below diagram.

<img src="https://assets.vantage.sh/blog/automate-jira-issues/jira-vantage.png" alt="A diagram that starts with the Vantage logo. The Vantage logo points to a symbol that represents a Python script. The Python script points to the Jira logo. The Jira logo has three arrows coming from it that point to an image of three Jira tasks. Each task says Vantage Cost Recommendations." width="500" height="auto">

See the [demo blog](https://www.vantage.sh/blog/automate-jira-issues) for a walkthrough of how to complete each step.

## Prerequisites

- Valid [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations) from either AWS, Azure, Datadog, or Kubernetes
- Base64-encoded Jira token and email address in the form of `useremail:api_token`
  - Export with `export JIRA_TOKEN=<BASE64_ENCODED_EMAIL_TOKEN>`

## Complete the Demo

1. Use the provided `main.py` file from this repo to create a script that queries the Vantage API for recommendations and sends them to Jira as issues.
2. Update the `timedelta` formula, or consider deploying the script on a scheduler, like Apache Airflow.

## References 

- [Vantage Blog](https://www.vantage.sh/blog/automate-jira-issues)
- [Basic auth Jira docs](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/)
- [Vantage Cost Recommendations API Endpoint](https://vantage.readme.io/reference/getrecommendations)
- [Cost Recommendations Documentation](https://docs.vantage.sh/cost_recommendations)
