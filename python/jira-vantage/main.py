import requests
import json
from datetime import datetime, timedelta
import os

# Jira information
# Add your Jira URL, which might differ from the below format
jira_url = "https://<YOUR_ORG>.atlassian.net/"
issue_type = "Task"

# Vantage information
vantage_headers = {
    "accept": "application/json",
    "authorization": f"Bearer {os.environ.get('VANTAGE_API_TOKEN')}"
}

# Map of providers and corresponding Jira project IDs
providers_projects = {
    "aws": "DAT",
    "datadog": "CI"
}

# Create a Jira issue
def create_jira_issue(project_key, summary, description):
    url = f"{jira_url}/rest/api/2/issue"
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {os.environ.get('JIRA_TOKEN')}"}
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type}
        }
    }
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers
    )
    if response.status_code == 201:
        print("Issue created successfully.")
        issue_key = response.json().get("key")
        print(f"Issue key: {issue_key}")
    else:
        print(f"Failed to create issue. Status code: {response.status_code}")
        print(response.json())
        
# Fetch recs from Vantage and create a Jira issue
def process_recommendations(provider, project_key):
    vantage_url = f"https://api.vantage.sh/v2/recommendations?provider={provider}"
    response = requests.get(vantage_url, headers=vantage_headers)
    if response.status_code == 200:
        recommendations = response.json().get("recommendations", [])
        current_time = datetime.utcnow()
        past_month = current_time - timedelta(days=30)

        for recommendation in recommendations:
            created_at = datetime.strptime(recommendation["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            if created_at >= past_month:
                service = recommendation["service"]
                description_text = recommendation["description"]
                potential_savings = float(recommendation["potential_savings"])

                summary = f"{service}: Vantage Cost Recommendations"
                description = f"""
                A cost recommendation was found for {service} in Vantage.

                {description_text}

                The recommendation has a potential savings of ${potential_savings:.2f}.

                [View all|https://console.vantage.sh/recommendations?provider={provider}] Vantage recommendations.
                """

                create_jira_issue(project_key, summary, description.strip())
    else:
        print(f"Failed to retrieve recommendations for {provider}. Status code: {response.status_code}")
        print(response.text)
        
# Iterate through the providers_projects map for each project
for provider, project_key in providers_projects.items():
    process_recommendations(provider, project_key)