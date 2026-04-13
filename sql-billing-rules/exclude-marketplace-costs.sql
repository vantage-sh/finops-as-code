-- title: "Exclude Marketplace Costs",

DELETE FROM costs
WHERE costs.cost_category = 'AWS Marketplace'
