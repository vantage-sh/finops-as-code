-- title: "Apply Discount Excluding Reservations (Azure)",

UPDATE costs 
SET costs.amount = costs.amount * 0.95
WHERE costs.provider = 'azure' 
AND LOWER(costs.resource_id) NOT LIKE '%/providers/microsoft.capacity/reservationorders%'
