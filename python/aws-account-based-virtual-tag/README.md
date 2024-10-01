# Automate AWS Account Name Tags

Many Vantage customers will use AWS accounts to partition their costs, but then want to allocate other shared costs to those accounts that may not live in those accounts, such as AWS Support fees. This lab will use the AWS Organizations API to retrieve a list of all of your accounts and automate the creation of a [Virtual Tag](https://docs.vantage.sh/virtual_tagging/) filtered to the Account ID of that account.

![Screenshot 2024-09-30 at 5 21 11 PM](https://github.com/user-attachments/assets/55fc3709-018c-4748-b7af-4a3758227bb2)

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- [AWS Integration](https://www.vantage.sh/integrations) set up in Vantage
- [AWS CLI](https://aws.amazon.com/cli/) configured
- [AWS Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#installation) installed

## Complete the Demo

Use the provided `virtual_tag_by_account.py` file from this repo to retrieve AWS account list and create a Virtual Tag for each account, filtered to the Account ID of that account.
