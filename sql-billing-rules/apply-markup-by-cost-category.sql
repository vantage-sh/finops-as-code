-- title: "Apply Markup by Cost Category",

UPDATE costs 
SET costs.amount = costs.amount * 1.10
WHERE costs.cost_category = 'Storage'
