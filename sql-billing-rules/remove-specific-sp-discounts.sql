-- title: "Remove arn:aws:savingsplans::004284483911:savingsp...",

UPDATE aws
SET aws."lineItem/LineItemType" = 'Usage'
WHERE aws."lineItem/LineItemType" = 'SavingsPlanCoveredUsage' AND aws."savingsPlan/SavingsPlanARN" = 'arn:aws:savingsplans::01234567890:savingsplan/abcdefg12345' -- replace with the actual savings plan ARN