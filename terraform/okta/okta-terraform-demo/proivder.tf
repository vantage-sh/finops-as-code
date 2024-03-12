terraform {
  required_providers {
    vantage = {
      source = "vantage-sh/vantage"
    }
    okta = {
      source = "okta/okta"
    }
  }
}

provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
}