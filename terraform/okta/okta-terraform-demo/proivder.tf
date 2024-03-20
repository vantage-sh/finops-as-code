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
  org_name    = var.okta_org_name
  base_url    = var.okta_base_url
  client_id   = var.okta_client_id
  scopes      = ["okta.groups.manage", "okta.users.manage", "okta.policies.manage"]
  private_key = "${path.module}/rsa.pem"
}
