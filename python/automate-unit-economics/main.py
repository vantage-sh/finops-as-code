import requests
from datetime import date
import psycopg2
import os

def fetch_orders(schema, table_name, current_date):
    try:
        # Replace with your database credentials
        conn = psycopg2.connect(
            dbname="<DB_NAME>",
            user="<USER>",
            password="<PASSWORD>",
            host="<HOST>",
            port="<PORT>"
        )

        cur = conn.cursor()

        # Execute the query with the current date
        query = f"SELECT * FROM {schema}.{table_name} WHERE date = %s"
        cur.execute(query, (current_date,))
        records = cur.fetchall()

        cur.close()
        conn.close()

        return records
    except Exception as e:
        print(f"Error fetching records from table {table_name}: {e}")
        return []
    
def update_business_metric(metric_id, payload):
    try:
        url = f"https://api.vantage.sh/v2/business_metrics/{metric_id}"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {os.environ.get('VANTAGE_API_TOKEN')}"
        }
        response = requests.put(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"Error updating business metric {metric_id}: {e}"
    
if __name__ == "__main__":
    # Get the current date
    current_date = date.today().isoformat()

    # Schema and table; adjust as needed
    schema = "public"
    table_name = "total_orders"

    # Fetch and update total orders
    orders = fetch_orders(schema, table_name, current_date)
    if orders:
        date_returned, total_orders_returned = orders[0]
        payload = {"values": [{"date": date_returned.isoformat(), "amount": total_orders_returned}]}
        metric_id = os.environ.get("ORDERS_METRIC_ID")
        if metric_id:
            response = update_business_metric(metric_id, payload)
            print("Vantage API response:", response)
        else:
            print("Business metric token not found.")
    else:
        print(f"No records found for {schema}.{table_name} for the current date.")