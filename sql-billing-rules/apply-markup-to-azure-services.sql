-- title: "Apply Markup to Azure Services",

UPDATE costs 
SET costs.amount = costs.amount * 1.10
WHERE costs.provider = 'azure' AND costs.service = 'Virtual Machines'
