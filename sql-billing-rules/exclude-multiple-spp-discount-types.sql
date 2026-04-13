-- title: "Exclude Multiple SPP Discount Types",

DELETE FROM costs 
WHERE costs.cost_type IN ('SppDiscount', 'UnamortizedSppDiscount')
