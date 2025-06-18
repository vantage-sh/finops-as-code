-- title: "+2% on AWS Marketplace",

UPDATE aws
SET aws."lineItem/UnblendedCost" = aws."lineItem/UnblendedCost" * '1.02'
WHERE aws."bill/BillingEntity" = 'AWS Marketplace'