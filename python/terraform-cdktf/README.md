# FinOps as Code with the Terraform CDK (CDKTF)

In this demo, we’ll focus on creating a reusable cloud cost reporting infrastructure. We’ll showcase how you can use [Cloud Development Kit for Terraform (CDKTF)](https://developer.hashicorp.com/terraform/cdktf) to create a Vantage cost reporting construct for managing a Vantage folder, saved filter, and Cost Report.

CDKTF takes the infrastructure you define and synthesizes it into JSON configuration files that are compatible with Terraform. Once deployed, Terraform uses those files to provision your infrastructure. You can use the CDKTF CLI to make deployments, and you can also use the configuration files directly.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)
- A Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`)
  - Export with `export VANTAGE_WORKSPACE_TOKEN=<YOUR_WORKSPACE_TOKEN>`

## Complete the Demo

1. Create a directory for your project and initialize a Python (or your language of choice) CDKTF project. Add the files from this repo to the directory.

    ```bash
    mkdir vantage-cdktf-example && cd vantage-cdktf-example 
    ``` 

2. Initialize the `vantage-sh/vantage` provider. Specify the `local` flag to use local state storage.

   ```bash
    cdktf init --template=python --local --providers="vantage-sh/vantage"
   ```

3. Deploy the configuration.
   
    ```bash
    cdktf deploy
    ```

## References 

- [Vantage blog](https://www.vantage.sh/blog/finops-as-code-terraform-cdk)
- [Vantage Query Language](https://docs.vantage.sh/vql)