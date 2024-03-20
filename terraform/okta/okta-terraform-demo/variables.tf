variable "okta_org_name" {
  type        = string
  description = "Okta org name"
  default     = "YOUR_OKTA_ORG"
}

variable "okta_base_url" {
  type        = string
  description = "Okta base url"
  default     = "okta.com"
}

variable "okta_client_id" {
  type        = string
  description = "Okta client ID"
  default     = "<YOUR_OKTA_CLIENT_ID>"
}

variable "vantage_workspace_token" {
  type        = string
  description = "Vantage workspace token"
  default     = "<YOUR_VANTAGE_WORKSPACE>"
}
