-- title: "Remove Costs for Specific AWS Accounts",

DELETE FROM aws 
WHERE aws.lineItem/UsageAccountId IN (
  '111111111111',
  '222222222222',
  '333333333333'
)
