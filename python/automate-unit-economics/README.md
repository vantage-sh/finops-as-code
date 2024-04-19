# Automate and Visualize Unit Economics

You work for an e-commerce company that wants to track certain business-related metrics along with their cloud infrastructure costs. You’ve observed that cloud costs typically surge during the week but drop on weekends. You want to view these metrics on top of your cloud costs to understand how your current cloud spending affects per unit costs. You have a view set up in a PostgreSQL database, called `total_orders`, that aggregates data from other tables. The workflow for this demo follows the below diagram.

<img src="https://assets.vantage.sh/blog/automate-unit-economics/automate-unit-economics-chart.png" alt="A diagram that starts with a database icon. The database has the PostgreSQL icon on top of it. An arrow points from the database to an icon of a script with the Python logo on it. The Python script has a symbol of a clock next to it. From the Python script, an arrow points to a symbol of a cloud with the Vantage logo that says Vantage API. From the Vantage API symbol, an arrow points to two icons that show representations of a line over them. The label for this last icon is Per Unit Costs." width="500" height="auto">

See the [demo blog](https://www.vantage.sh/blog/automate-unit-economics) for a walkthrough of how to complete each step.

## Prerequisites

- Valid Read/Write [Vantage API token](https://vantage.readme.io/reference/authentication)
  - Export with `export VANTAGE_API_TOKEN=<YOUR_API_TOKEN>`
- At least one [connected provider](https://www.vantage.sh/integrations)
- A preconfigured business metric. To create the initial business metric, you can create it directly in [Vantage](https://docs.vantage.sh/per_unit_costs), or you can send the following POST call to the `/business_metrics` [endpoint](https://vantage.readme.io/reference/createbusinessmetric).
  - Export with `export ORDERS_METRIC_ID=<BUSINESS_METRIC_TOKEN>`

## Complete the Demo

1. Use the provided `main.py` file from this repo to create a script that queries a PostgreSQL database and sends the data to the Vantage API.
2. Update the PostgreSQL credentials within the script and any table names to match your configuration.
3. Deploy the script daily on a scheduler, like Apache Airflow, or create a cron job so that new information is provided to the Vantage API each day.

## References 

- [Vantage Blog](https://www.vantage.sh/blog/automate-unit-economics)
- [Vantage Business Metrics API Endpoint](https://vantage.readme.io/reference/createbusinessmetric)
- [Business Metrics Documentation](https://docs.vantage.sh/per_unit_costs)
- [`psycopg2` Documentation](https://www.psycopg.org/docs/usage.html)