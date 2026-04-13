-- title: "Exclude SPP Discounts",

DELETE FROM costs 
WHERE costs.cost_type = 'SppDiscount'
