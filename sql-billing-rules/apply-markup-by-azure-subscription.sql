-- title: "Apply Markup by Azure Subscription",

UPDATE costs 
SET costs.amount = costs.amount * 1.10
WHERE costs.provider = 'azure' AND costs.resource_account_id = 'your-subscription-id'
