import requests
import boto3
import os


url = "https://api.vantage.sh/v2/virtual_tag_configs"
VANTAGE_API_TOKEN = os.environ.get("VANTAGE_API_TOKEN")

session = boto3.session.Session()
org = session.client('organizations')

# get list of accounts
paginator = org.get_paginator('list_accounts')
page_iterator = paginator.paginate()

accounts = []
for page in page_iterator:
    for acct in page['Accounts']:
        accounts.append({
            "filter": f"costs.provider = 'aws' AND costs.account_id = '{acct['Id']}'",
            "name": "".join(c for c in acct['Name'] if c not in "'?!")
        })

payload = {
    "overridable": False,
    "key": "AWS Account Names",
    "values": accounts
}
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {VANTAGE_API_TOKEN}"
}

response = requests.post(url, json=payload, headers=headers)
response.raise_for_status()
print(response.text)
