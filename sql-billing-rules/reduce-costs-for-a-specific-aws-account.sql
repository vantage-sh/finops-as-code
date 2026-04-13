-- title: "Reduce Costs for a Specific AWS Account",

UPDATE aws 
SET aws.lineItem/UnblendedCost = aws.lineItem/UnblendedCost * 0.50
WHERE aws.lineItem/UsageAccountId = '111111111111'
