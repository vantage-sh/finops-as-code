-- title: "Exclude Partner Earned Credit (Azure CSP)",

DELETE FROM costs 
WHERE costs.provider = 'azure_csp' AND costs.cost_type = 'PartnerEarnedCredit'
