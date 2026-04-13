-- title: "Rename a Service",

UPDATE costs
SET costs.service = 'Custom Compute'
WHERE costs.provider = 'aws' AND costs.service = 'Amazon Elastic Compute Cloud - Compute'
