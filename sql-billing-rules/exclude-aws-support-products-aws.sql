-- title: "Exclude AWS Support Products (AWS)",

DELETE FROM aws 
WHERE aws.lineItem/ProductCode IN ('AWSSupportBusiness', 'AWSSupportEnterprise', 'AWSSupportDeveloper')
