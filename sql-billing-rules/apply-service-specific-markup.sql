-- title: "Apply Service-Specific Markup",

UPDATE costs 
SET costs.amount = costs.amount * 1.05
WHERE costs.service IN ('Amazon Relational Database Service', 'AWS Lambda')
