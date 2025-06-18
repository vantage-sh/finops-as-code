-- title: "Undiscount SavingsPlanCoveredUsage",

UPDATE aws
SET aws."lineItem/LineItemType" = 'Usage'
WHERE aws."lineItem/LineItemType" = 'SavingsPlanCoveredUsage'