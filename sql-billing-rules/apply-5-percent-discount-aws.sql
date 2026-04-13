-- title: "Apply a 5% Discount (AWS)",

UPDATE aws
SET aws.lineItem/UnblendedCost = aws.lineItem/UnblendedCost * 0.95
WHERE aws.lineItem/LineItemType != 'Credit'
