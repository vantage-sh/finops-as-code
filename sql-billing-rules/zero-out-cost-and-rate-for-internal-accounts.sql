-- title: "Zero Out Cost and Rate for Internal Accounts",

UPDATE aws 
SET aws.lineItem/UnblendedCost = '0', aws.lineItem/UnblendedRate = '0'
WHERE aws.lineItem/UsageAccountId IN ('111111111111', '222222222222', '333333333333')
