-- title: "Unamortize Savings Plans for a Specific Account",

UPDATE aws 
SET aws.lineItem/LineItemType = 'Usage', aws.savingsPlan/SavingsPlanARN = NULL
WHERE aws.lineItem/LineItemType = 'SavingsPlanCoveredUsage'
AND aws.savingsPlan/SavingsPlanARN LIKE 'arn:aws:savingsplans::111111111111%'
