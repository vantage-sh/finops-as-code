locals {
  cost_centers   = yamldecode(file("cost-centers.yaml")).cost_centers
  business_units = toset([for k, cost_center in local.cost_centers : cost_center.business_unit])
  teams          = toset([for k, cost_center in local.cost_centers : cost_center.team])

  all_cc = flatten([
    for cc, cc_info in local.cost_centers : [
      {
        cost_center   = cc
        business_unit = cc_info.business_unit
        team          = cc_info.team
      }
    ]
  ])
}

resource vantage_segment "organization"{
    title = "Company"
    description = "Top organization-level segment"
    workspace_token = var.workspace_token
    priority = 100
}

resource vantage_segment "bu"{
    for_each = local.business_units
    title = each.key
    description = "${each.key} segment"
    parent_segment_token = vantage_segment.organization.token
    priority = 100
}

resource vantage_segment "child"{
    for_each = local.cost_centers
    title = each.value.team
    description = "${each.value.team} segment"
    filter = "costs.provider = 'gcp' AND (tags.name, tags.value) IN (('cost_center', '${each.key}'))"
    parent_segment_token = vantage_segment.bu[each.value.business_unit].token
    priority = 100
}