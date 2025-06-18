-- title: "Re-Rate to Public Price",

UPDATE aws
SET aws."lineItem/UnblendedCost" = aws."pricing/publicOnDemandCost", aws."lineItem/UnblendedRate" = aws."pricing/publicOnDemandRate"
