<div align="center">

<h1>FinOps as Code: Demos and Tutorials</h1>

<img src="/assets/finops-as-code.jpg" alt="Header image" width="600" height="auto">

</div>

## What Is FinOps as Code?

This repository contains tutorials and demos for implementing _FinOps as Code_ in your organization.

FinOps as Code is the integration of financial operations (FinOps) principles with modern cloud-native practices. FinOps as Code encourages practitioners to manage cloud costs and optimize spending patterns in a programmatic and automated manner.

Like its close cousin, Infrastructure as Code, FinOps as Code supports automation scripts and cloud-native technologies so that organizations can implement FinOps practices directly into their software development lifecycle.

## About This Repository

This repository contains API Python tutorials (within the `/python` directory), Terraform tutorials (within the `/terraform` directory), and CloudFormation templates for multi-account AWS setups (within the `/cloudformation` directory). Each demo contains a README with any prerequisites or requirements. 

To use the demos provided here, create a local clone of this repo.

## Python Dependencies

Each Python demo's README names the one or two packages that demo needs, so you can install only those:

```bash
pip install boto3
```

If you would rather have one environment that runs every Python demo, the root `pyproject.toml` lists them all. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

`uv sync` matches the environment to that file exactly, so it removes packages it does not declare. To add them alongside what you already have, use `uv pip install -r pyproject.toml` instead.

Two demos generate their provider package with a CLI rather than installing it from PyPI, so it is not in `pyproject.toml`: `pulumi/intro-to-pulumi` uses `pulumi package add`, and `python/terraform-cdktf` uses `cdktf get`. Each README covers the step.

## Vantage API Authentication

Each demo requires access to the Vantage API. Follow the steps in the [Vantage API documentation](https://docs.vantage.sh/api/authentication) on how to create a user authentication token.

## Contributing

If there are additional tutorials or demos you want to see here, [create a tutorial request](https://github.com/vantage-sh/finops-as-code/issues) via the Issues section of this repo.

## Additional Resources

- [Vantage API Documentation](https://docs.vantage.sh/api)
- [Vantage Product Documentation](https://docs.vantage.sh/)
  - [VQL (Vantage Query Language)](https://docs.vantage.sh/vql)
  - [Terraform Provider Intro](https://docs.vantage.sh/terraform)
- [Vantage Terraform Provider](https://registry.terraform.io/providers/vantage-sh/vantage/latest/docs)
- [Vantage Terraform Repo](https://github.com/vantage-sh/terraform-provider-vantage)
- [Vantage Blog](https://www.vantage.sh/blog/)
- [Vantage Sign-up](https://console.vantage.sh/signup)
- [Vantage Status](https://status.vantage.sh/)
