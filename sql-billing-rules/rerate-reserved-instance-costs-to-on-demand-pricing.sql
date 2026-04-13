-- title: "Rerate Reserved Instance Costs to On-Demand Pricing",

UPDATE aws 
SET aws.lineItem/UnblendedCost = aws.pricing/publicOnDemandCost, aws.lineItem/UnblendedRate = aws.pricing/publicOnDemandRate
WHERE aws.lineItem/LineItemType = 'DiscountedUsage'
AND (
  aws.reservation/ReservationARN LIKE '%111111111111%'
  OR aws.reservation/ReservationARN LIKE '%222222222222%'
)
