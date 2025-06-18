-- title: "Remove RI/SP Discounts"

UPDATE aws
SET aws."lineItem/LineItemType" = 'Usage' 
WHERE aws."lineItem/LineItemType" IN ('SavingsPlanCoveredUsage', 'DiscountedUsage') AND aws."savingsPlan/SavingsPlanARN" || aws."reservation/ReservationARN" NOT LIKE '%:' || aws."lineItem/UsageAccountId" || ':%'
