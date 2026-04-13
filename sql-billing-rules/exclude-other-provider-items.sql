-- title: "Exclude Other Provider Items",

DELETE FROM costs 
WHERE costs.provider = 'temporal' AND costs.service = 'Temporal Cloud' AND costs.cost_sub_category = 'Actions'
