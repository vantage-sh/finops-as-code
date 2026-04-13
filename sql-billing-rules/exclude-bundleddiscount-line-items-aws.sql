-- title: "Exclude BundledDiscount Line Items (AWS)",

DELETE FROM aws 
WHERE aws.lineItem/LineItemType = 'BundledDiscount'
