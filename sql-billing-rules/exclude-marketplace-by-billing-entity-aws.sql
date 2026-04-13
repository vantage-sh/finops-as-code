-- title: "Exclude Marketplace by Billing Entity (AWS)",

DELETE FROM aws 
WHERE aws.bill/BillingEntity = 'AWS Marketplace'
