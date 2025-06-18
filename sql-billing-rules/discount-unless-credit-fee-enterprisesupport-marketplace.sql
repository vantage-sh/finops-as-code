-- title: "9.5% discount unless Credit, Fee, Enterprise Support or Marketplace Purchase",


UPDATE aws
SET aws."lineItem/UnblendedCost" = aws."lineItem/UnblendedCost" * '0.095'
WHERE 
aws."lineItem/ProductCode" != 'AwsPremiumSupport' 
AND aws."lineItem/LineItemType" != 'Credit' 
AND aws."lineItem/LineItemType" != 'Fee' 
AND aws."bill/BillingEntity" != 'AWS Marketplace'