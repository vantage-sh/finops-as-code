-- title: "Exclude SPP/EDP Discount Line Items (AWS)",

DELETE FROM aws
WHERE aws.lineItem/LineItemType IN ('Discount', 'Credit')
AND (
  aws.lineItem/LineItemDescription ILIKE '%Enterprise Discount Program%'
  OR aws.lineItem/LineItemDescription ILIKE '%Solution Provider%'
)
