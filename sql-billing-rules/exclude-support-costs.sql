-- title: "Exclude Support Costs",

DELETE FROM costs 
WHERE costs.service = 'AWS Support (Business)'
