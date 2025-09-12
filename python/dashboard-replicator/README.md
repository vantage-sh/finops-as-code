# Vantage Dashboard Replicator

## Overview

[![Dashboard Replicator Demo](https://cdn.loom.com/sessions/thumbnails/5080dcc4e91345eaa15eac19add2f86f-42c1eff4962e2270-full-play.gif)](https://www.loom.com/share/5080dcc4e91345eaa15eac19add2f86f?sid=d228bb80-ecfa-4a85-aa10-fd4880e71e80)

The **Vantage Dashboard Replicator** is a Python script that enables you to **replicate an entire Vantage dashboard**, including all its **underlying reports** (e.g., Cost Reports, Resource Reports, etc.), across different workspaces. You can clone dashboards:

- **Within the same Vantage account** (to a different workspace)
- **Between different Vantage accounts** (ideal for teams managing multiple orgs)

This tool is particularly useful for teams using **FinOps-as-Code**, enabling consistent dashboard and report structures across environments (e.g., production vs staging accounts, or across business units).

## Requirements

- Python 3.7+
- `requests` library (for Vantage API calls)
- Valid Vantage **API tokens** for source and target workspaces

Install dependencies:

```bash
pip install requests
```

## Setup

1. Clone this repo:

```bash
git clone https://github.com/vantage-sh/finops-as-code.git
cd finops-as-code/python/dashboard-replicator
```

2. Retrieve the following variables. You can set the following as environment variables, or use them directly within the prompts:

```bash
export SOURCE_API_KEY="your-source-api-key"
export TARGET_API_KEY="your-target-api-key"
export SOURCE_WORKSPACE_ID="your-source-workspace-id"
export TARGET_WORKSPACE_ID="your-target-workspace-id"
export DASHBOARD_ID="dashboard-id-to-clone"
```

> You can retrieve these values from the Vantage web UI or API.

## Usage

Run the script with:

```bash
python vantage_dashboard_replicator.py
```

The script will:

1. Authenticate against the Vantage API using the source and target API keys.
2. Fetch the specified dashboard and all its associated reports from the source workspace.
3. Recreate the reports in the target workspace.
4. Rebuild a new dashboard in the target workspace using the cloned reports.


## Notes & Limitations

- This script can only add existing Financial Commitment Reports, as there is not a supported API to create new FCRs
- Tags and linked entities (e.g., saved filters) may require manual verification after cloning.
- Rate limits on the Vantage API may apply for very large dashboards.

## Support

For help, reach out to [support@vantage.sh](mailto:support@vantage.sh) or open an issue in the [GitHub repo](https://github.com/vantage-sh/finops-as-code/issues).
