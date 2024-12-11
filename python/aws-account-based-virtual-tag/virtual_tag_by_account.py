import requests
import boto3
import os


url = "https://api.vantage.sh/v2/virtual_tag_configs"
VANTAGE_ACCESS_TOKEN = os.environ.get("VANTAGE_ACCESS_TOKEN")

session = boto3.session.Session()
client = session.client('sts')
org = session.client('organizations')

# get list of accounts
paginator = org.get_paginator('list_accounts')
page_iterator = paginator.paginate()

accounts = []
for page in page_iterator:
    for acct in page['Accounts']:
        accounts.append({
            "filter": f"costs.provider = 'aws' AND costs.account_id = '{acct['Id']}'",
            "name": acct['Name'].replace("'?!", "")
        })

payload = {
    "overridable": False,
    "key": "AWS Account Names",
    "values": accounts
}
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {VANTAGE_ACCESS_TOKEN}"
}

response = requests.post(url, json=payload, headers=headers)
print(response.text)





