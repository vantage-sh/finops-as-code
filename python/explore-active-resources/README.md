# Exploring Active Resources

An _active resource_ is a resource, such as a virtual machine, that is currently generating costs within a cloud account. These resources can come from any cloud provider, such as an Amazon EC2 instance or a Confluent cluster. It's important to know which resources are active and generating costs; otherwise, you could run into instances where things like S3 buckets [start generating ridiculously high costs](https://www.vantage.sh/blog/how-to-avoid-unexpected-s3-costs), and next thing you know you're paying thousands in unexpected costs.

In this tutorial, we walk through how to use the [Vantage API](https://www.vantage.sh/blog/vantage-launches-api-resource-costs) to explore your active resources across any of your ingested cloud providers. We provide a script that lets you interact and view pivoted cost data across resource type, provider, region, and more. You can use these insights to understand where your organization is spending the most and what resources are currently generating the most costs. Consider this tutorial an introduction to even deeper analysis you can do with this API.

See the [demo blog](https://www.vantage.sh/blog/finops-as-code-active-resources) for a walkthrough of how to complete each step.

## Prerequisites

- Valid [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations) with [active resources](https://docs.vantage.sh/active_resources) 

## Complete the Demo

Open the Jupyter Notebook and follow along with the steps on how to import your data and use `pandas` and other data visualization libraries to look at insights about your data.

## References 

- [Vantage Blog](https://www.vantage.sh/blog/finops-as-code-active-resources)
- [Vantage Resources API Endpoint](https://vantage.readme.io/reference/getreportresources)
- [Active Resources Documentation](https://docs.vantage.sh/active_resources)
