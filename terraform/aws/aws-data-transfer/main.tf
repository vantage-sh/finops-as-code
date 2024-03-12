locals {
  filter = <<FILTER
(costs.provider = 'aws' 
AND costs.service = 'Amazon Elastic Compute Cloud - Compute' 
AND costs.category = 'Data Transfer'
OR
costs.provider = 'aws' 
AND costs.service = 'Amazon Virtual Private Cloud' 
AND costs.category = 'Data Transfer'
OR
costs.provider = 'aws' 
AND costs.service = 'AWS Lambda' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'AWS Step Functions' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon API Gateway' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Elastic Container Service' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Elastic Container Service' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Elastic Load Balancing' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Glacier' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Relational Database Service' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Simple Email Service' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'Amazon Simple Storage Service' 
AND costs.category = 'Data Transfer'
OR 
costs.provider = 'aws' 
AND costs.service = 'NAT Gateways' 
AND costs.category = 'Data Transfer')
FILTER
}

resource "vantage_cost_report" "data_transfer" {
  filter          = local.filter
  title           = "AWS Data Transfer Breakdown"
  workspace_token = var.workspace_token
}
