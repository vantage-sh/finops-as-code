-- title: "Exclude Reservation Fees for Specific Accounts",

DELETE FROM aws
WHERE aws.lineItem/LineItemType = 'RIFee'
AND (
  aws.reservation/ReservationARN LIKE '%:111111111111:%'
  OR aws.reservation/ReservationARN LIKE '%:222222222222:%'
)
