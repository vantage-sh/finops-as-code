-- title: "Apply Discount to NCE Licenses (Azure CSP)",

UPDATE costs 
SET costs.amount = costs.amount * 0.95
WHERE costs.provider = 'azure_csp' AND costs.service = 'NCE License' AND costs.cost_type = 'Purchase'
