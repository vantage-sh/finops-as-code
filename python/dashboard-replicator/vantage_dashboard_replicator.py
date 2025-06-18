import requests
import json
import pprint
import os
from simple_term_menu import TerminalMenu

# Vantage API 
url = "https://api.vantage.sh/v2"

def headers(token):
    return {
        "accept": "application/json",
        "authorization": f"Bearer {token}"
    }

def selector_menu(options, title=None):
    """
    Single-selection menu.
    title: optional string to display at top
    """
    if title:
        print(title)
    menu = TerminalMenu(options)
    selected_index = menu.show()
    selected = options[selected_index]
    print("> ", selected)
    return selected

def multi_selector_menu(options, title=None):
    """
    Multi-selection menu.
    title: optional string to display at top
    Press <Space> to select, <Enter> to finish.
    Returns a list of selected items.
    """
    if title:
        print(title)
    menu = TerminalMenu(options, multi_select=True, show_multi_select_hint=True)
    selected_indices = menu.show()
    # If user cancels or presses Enter without selecting anything,
    # selected_indices might be []. So handle that gracefully.
    selected_items = [options[i] for i in selected_indices] if selected_indices else []
    if selected_items:
        print("> Selected:", ", ".join(selected_items))
    else:
        print("> No dashboards selected.")
    return selected_items

def choose_workspace(api_token):
    """
    Shows a single-selection menu of workspaces for the given account token.
    Returns the token of the selected workspace.
    """
    response = requests.get(f"{url}/workspaces", headers=headers(api_token))
    workspaces = response.json()
    workspace_names = [ws["name"] for ws in workspaces["workspaces"]]

    selected_workspace = selector_menu(workspace_names, "Select a workspace:")
    workspace_token = next(
        (ws["token"] for ws in workspaces["workspaces"] if ws["name"] == selected_workspace),
        None
    )
    return workspace_token

def copy_dashboards(source_api_token, destination_api_token):
    # Step 4: Choose source workspace
    print("\nSelect the workspace *from which* you want to copy dashboards:")
    source_workspace_token = choose_workspace(source_api_token)

    # Step 5: Show all dashboards in that workspace, allowing multiple selections
    dashboards_data = requests.get(f"{url}/dashboards", headers=headers(source_api_token)).json()
    all_dashboards = dashboards_data["dashboards"]

    source_dashboard_titles = [
        d["title"] for d in all_dashboards 
        if d["workspace_token"] == source_workspace_token
    ]

    # Let the user choose multiple dashboards
    selected_dashboard_titles = multi_selector_menu(
        source_dashboard_titles,
        title="Select the dashboard(s) you would like to copy (Press SPACE to select, ENTER to confirm):"
    )

    # If none selected, exit gracefully this copy session
    if not selected_dashboard_titles:
        print("\nNo dashboards selected for copying.")
        return

    # Step 6: Choose destination workspace
    print("\nSelect the workspace you would like the dashboard(s) copied TO:")
    destination_workspace_token = choose_workspace(destination_api_token)

    # Step 7: For each chosen dashboard, replicate
    for dash_title in selected_dashboard_titles:
        print(f"\n=== Copying dashboard: {dash_title} ===")

        # Get the token for this specific dashboard
        dash_token = next((d["token"] for d in all_dashboards if d["title"] == dash_title), None)
        if not dash_token:
            print(f"Could not find dashboard token for '{dash_title}' - skipping.")
            continue

        # Grab the original dashboard object
        og_dashboard_resp = requests.get(f"{url}/dashboards/{dash_token}", headers=headers(source_api_token))
        og_dashboard = og_dashboard_resp.json()

        # Gather the original widgets (report tokens)
        tokens = og_dashboard["widget_tokens"]
        report_names = [w["title"] for w in og_dashboard["widgets"]]

        print("------")
        print(len(tokens), "reports to create: ", ", ".join(report_names))
        print("------")

        # Create a folder in the destination to store these new Cost/Resource Reports
        folder_payload = {
            "title": og_dashboard["title"],
            "workspace_token": destination_workspace_token
        }
        folder_resp = requests.post(f"{url}/folders", json=folder_payload, headers=headers(destination_api_token))
        folder = folder_resp.json()
        print("New Folder Created:", folder["title"], f"({folder['token']}) to store all Cost Reports")

        # Duplicate all the Cost/Resource reports
        widget_list = []
        successful_report_names = []
        unsuccessful_report_names = []

        for token in tokens:
            print("------")
            # Resource Report
            if token.startswith("prvdr_rsrc_rprt"):
                resource_report_resp = requests.get(f"{url}/resource_reports/{token}", headers=headers(source_api_token))
                if resource_report_resp.status_code != 200:
                    print(f"Error retrieving Resource Report {token}")
                    unsuccessful_report_names.append(token)
                    continue

                resource_report = resource_report_resp.json()
                print("Copying Resource Report:", resource_report["title"], f"({resource_report['token']})")

                new_resource_report = {
                    "title": resource_report["title"],
                    "workspace_token": destination_workspace_token,
                    "filter": resource_report["filter"]
                }

                try:
                    create_new_resource_report_resp = requests.post(
                        f"{url}/resource_reports",
                        json=new_resource_report,
                        headers=headers(destination_api_token)
                    )
                    create_new_resource_report = create_new_resource_report_resp.json()

                    if create_new_resource_report_resp.status_code == 201:
                        widget_list.append(create_new_resource_report["token"])
                        successful_report_names.append(create_new_resource_report["title"])
                        print("Successfully created", create_new_resource_report["title"], 
                              "in destination (", create_new_resource_report["token"], ")")
                    else:
                        error_msg = create_new_resource_report.get("errors", "Unknown error")
                        unsuccessful_report_names.append(new_resource_report["title"])
                        print("Error creating Resource Report", new_resource_report["title"], ":", error_msg)
                except Exception as e:
                    unsuccessful_report_names.append(new_resource_report["title"])
                    print("Error creating Resource Report:", e)

            # Cost Report
            elif token.startswith("rprt"):
                cost_report_resp = requests.get(f"{url}/cost_reports/{token}", headers=headers(source_api_token))
                if cost_report_resp.status_code != 200:
                    print(f"Error retrieving Cost Report {token}")
                    unsuccessful_report_names.append(token)
                    continue

                cost_report = cost_report_resp.json()
                print("Copying Cost Report:", cost_report["title"], f"({cost_report['token']})")

                new_cost_report = {
                    "title": cost_report["title"],
                    "workspace_token": destination_workspace_token,
                    "groupings": cost_report["groupings"],
                    "filter": cost_report["filter"],
                    "folder_token": folder["token"],
                    "settings": cost_report["settings"],
                    "previous_period_start_date": cost_report["previous_period_start_date"],
                    "previous_period_end_date": cost_report["previous_period_end_date"],
                    "start_date": cost_report["start_date"],
                    "end_date": cost_report["end_date"],
                    "date_interval": cost_report["date_interval"],
                    "chart_type": cost_report["chart_type"],
                    "date_bin": cost_report["date_bin"]
                }

                # Remove 'usage_unit' from groupings if present
                if new_cost_report["groupings"]:
                    groupings_list = new_cost_report["groupings"].split(",")
                    groupings_list = [g for g in groupings_list if g != "usage_unit"]
                    new_cost_report["groupings"] = ",".join(groupings_list)

                try:
                    create_new_cost_report_resp = requests.post(
                        f"{url}/cost_reports",
                        json=new_cost_report,
                        headers=headers(destination_api_token)
                    )
                    create_new_cost_report = create_new_cost_report_resp.json()

                    if create_new_cost_report_resp.status_code == 201:
                        widget_list.append(create_new_cost_report["token"])
                        successful_report_names.append(create_new_cost_report["title"])
                        print("Successfully created", create_new_cost_report["title"], 
                              "in destination (", create_new_cost_report["token"], ")")
                    else:
                        error_msg = create_new_cost_report.get("errors", "Unknown error")
                        unsuccessful_report_names.append(new_cost_report["title"])
                        print("Error creating Cost Report", new_cost_report["title"], ":", error_msg)

                except Exception as e:
                    unsuccessful_report_names.append(new_cost_report["title"])
                    print("Error creating Cost Report:", e)

            # Financial Commitment Report
            elif token.startswith("fncl_cmnt_rprt"):
                fcr_resp = requests.get(f"{url}/financial_commitment_reports/{token}", headers=headers(source_api_token))
                if fcr_resp.status_code != 200:
                    print(f"Error retrieving Financial Commitment Report {token}")
                    unsuccessful_report_names.append(token)
                    continue

                fcr = fcr_resp.json()
                print("Copying Financial Commitment Report:", fcr["title"], f"({fcr['token']})")

                # Build the payload for the new Financial Commitment Report.
                new_fcr_payload = {
                    "title": fcr["title"],
                    "workspace_token": destination_workspace_token,
                    "filter": fcr["filter"],
                    # Add additional fields if required based on the API reference:
                    # e.g., "commitment_duration": fcr.get("commitment_duration"),
                    #       "commitment_threshold": fcr.get("commitment_threshold"),
                }

                try:
                    create_new_fcr_resp = requests.post(
                        f"{url}/financial_commitment_reports",
                        json=new_fcr_payload,
                        headers=headers(destination_api_token)
                    )
                    create_new_fcr = create_new_fcr_resp.json()

                    if create_new_fcr_resp.status_code == 201:
                        widget_list.append(create_new_fcr["token"])
                        successful_report_names.append(create_new_fcr["title"])
                        print("Successfully created", create_new_fcr["title"],
                              "in destination (", create_new_fcr["token"], ")")
                    else:
                        error_msg = create_new_fcr.get("errors", "Unknown error")
                        unsuccessful_report_names.append(new_fcr_payload["title"])
                        print("Error creating Financial Commitment Report", new_fcr_payload["title"], ":", error_msg)
                except Exception as e:
                    unsuccessful_report_names.append(new_fcr_payload["title"])
                    print("Error creating Financial Commitment Report:", e)

            # Kubernetes Efficiency Report
            elif token.startswith("kbnts_eff_rprt"):
                ker_resp = requests.get(f"{url}/kubernetes_efficiency_reports/{token}", headers=headers(source_api_token))
                if ker_resp.status_code != 200:
                    print(f"Error retrieving Kubernetes Efficiency Report {token}")
                    unsuccessful_report_names.append(token)
                    continue
                    
                ker = ker_resp.json()
                print("Copying Kubernetes Report:", ker["title"], f"({ker['token']})")

                # Build the payload for the new Kubernetes Efficiency Report.
                new_ker_payload = {
                    "title": ker["title"],
                    "workspace_token": destination_workspace_token,
                    "filter": ker["filter"],
                    "aggregated_by": ker["aggregated_by"],
                    "date_interval": ker["date_interval"]
                }

                try:
                    create_new_ker_resp = requests.post(
                        f"{url}/kubernetes_efficiency_reports",
                        json=new_ker_payload,
                        headers=headers(destination_api_token)
                    )
                    create_new_ker = create_new_ker_resp.json()

                    if create_new_ker_resp.status_code == 201:
                        widget_list.append(create_new_ker["token"])
                        successful_report_names.append(create_new_ker["title"])
                        print("Successfully created", create_new_ker["title"],
                              "in destination (", create_new_ker["token"], ")")
                    else:
                        error_msg = create_new_ker.get("errors", "Unknown error")
                        unsuccessful_report_names.append(new_ker_payload["title"])
                        print("Error creating Kubernetes Efficiency Report", new_ker_payload["title"], ":", error_msg)
                except Exception as e:
                    unsuccessful_report_names.append(new_ker_payload["title"])
                    print("Error creating Kubernetes Efficiency Report:", e)

            # Network Flow Report
            elif token.startswith("ntflw_lg_rprt"):
                nfr_resp = requests.get(f"{url}/network_flow_reports/{token}", headers=headers(source_api_token))
                if nfr_resp.status_code != 200:
                    print(f"Error retrieving Network Flow Report {token}")
                    unsuccessful_report_names.append(token)
                    continue
                    
                nfr = nfr_resp.json()
                print("Copying Kubernetes Report:", nfr["title"], f"({nfr['token']})")

                # Build the payload for the new Network Flow Report.
                new_nfr_payload = {
                    "title": nfr["title"],
                    "workspace_token": destination_workspace_token,
                    "filter": nfr["filter"],
                    "aggregated_by": nfr["aggregated_by"],
                    "date_interval": nfr["date_interval"]
                }

                try:
                    create_new_nfr_resp = requests.post(
                        f"{url}/network_flow_reports",
                        json=new_nfr_payload,
                        headers=headers(destination_api_token)
                    )
                    create_new_nfr = create_new_nfr_resp.json()

                    if create_new_nfr_resp.status_code == 201:
                        widget_list.append(create_new_nfr["token"])
                        successful_report_names.append(create_new_nfr["title"])
                        print("Successfully created", create_new_nfr["title"],
                              "in destination (", create_new_nfr["token"], ")")
                    else:
                        error_msg = create_new_nfr.get("errors", "Unknown error")
                        unsuccessful_report_names.append(new_nfr_payload["title"])
                        print("Error creating Network Flow Report", new_nfr_payload["title"], ":", error_msg)
                except Exception as e:
                    unsuccessful_report_names.append(new_nfr_payload["title"])
                    print("Error creating Network Flow Report:", e)

            else:
                print(f"No logic in this script for report token {token}, skipping.")
                unsuccessful_report_names.append(token)

        # Finally, create the new dashboard
        dashboard_payload = {
            "widget_tokens": widget_list,
            "title": og_dashboard["title"],
            "workspace_token": destination_workspace_token,
            "date_interval": "last_6_months"  # Or whatever default you prefer
        }
        new_dashboard_resp = requests.post(
            f"{url}/dashboards/",
            json=dashboard_payload,
            headers=headers(destination_api_token)
        )
        new_dashboard = new_dashboard_resp.json()

        if new_dashboard_resp.status_code == 201:
            print("------")
            print("New Dashboard Created:", new_dashboard["title"], f"({new_dashboard['token']})")
            print("Widgets added to dashboard:", ", ".join(successful_report_names))
            if unsuccessful_report_names:
                print("Widgets that were NOT successfully recreated:", ", ".join(unsuccessful_report_names))
        else:
            print("Error creating the new dashboard for:", dash_title)
            print(new_dashboard.get("errors", "Unknown error"))
    
    print("\nAll selected dashboards have been processed.")

# --------------------
# Main Script Logic
# --------------------

print("Welcome to the Vantage Dashboard Copying Machine(TM)")

# Step 1: Decide if same or different Vantage accounts
script_types = [
    "Copy dashboard(s) across workspaces in the same Vantage Account",
    "Copy dashboard(s) across different Vantage Accounts"
]
selected_copy_type = selector_menu(script_types, "Select what you would like to do:")

# Step 2: Get source API token (once)
source_api_token = input("Enter your source account API token (hit ENTER to use your VANTAGE_API_TOKEN envvar): ")
if not source_api_token:  # If blank, fall back to env var
    source_api_token = os.environ.get("VANTAGE_API_TOKEN")

# Step 3: If copying across different accounts, get destination token (else same as source)
if selected_copy_type == "Copy dashboard(s) across different Vantage Accounts":
    destination_api_token = input("Enter your destination account API token (hit ENTER to use your VANTAGE_API_TOKEN envvar): ")
    if not destination_api_token:
        destination_api_token = os.environ.get("VANTAGE_API_TOKEN")
else:
    destination_api_token = source_api_token

# Main loop for copying dashboards
while True:
    copy_dashboards(source_api_token, destination_api_token)
    
    # Ask the user whether to exit or continue
    next_action = selector_menu(
        ["Copy more dashboards", "Exit"],
        "What would you like to do next?"
    )
    if next_action == "Exit":
        print("Exiting. Happy Cloud Costing from Vantage!")
        break