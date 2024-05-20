# AWS S3 Cost Overruns

At the end of April, a [blog](https://medium.com/@maciej.pocwierz/how-an-empty-s3-bucket-can-make-your-aws-bill-explode-934a383cb8b1) went viral detailing how an empty S3 bucket suddenly incurred massive charges due to unauthorized incoming requests. 

In Vantage, you can view S3 costs segmented by bucket, region, storage class, custom tags, and more. Build this report to monitor S3 API requests, grouped by region and resource.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- AWS as a [connected provider](https://www.vantage.sh/integrations/aws)

## Create the Cost Report

1. Update `variables.tf` with a Vantage [workspace token](https://console.vantage.sh/settings/workspaces) (e.g., `wrkspc_12345`). 
2. Deploy this configuration with `terraform apply`.

## Reference

- [Vantage blog](https://www.vantage.sh/blog/how-to-avoid-unexpected-s3-costs)
- [Vantage Terraform provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Query Language](https://docs.vantage.sh/vql)
