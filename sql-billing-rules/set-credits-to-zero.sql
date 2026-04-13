-- title: "Set Credits to Zero",

UPDATE costs 
SET costs.amount = 0
WHERE costs.cost_type = 'Credit'
