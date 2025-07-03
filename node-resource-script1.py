import subprocess
import json
import shutil
from datetime import datetime, timedelta, timezone
import pandas as pd

# Find Azure CLI executable
az_path = shutil.which("az") or shutil.which("az.cmd")
if not az_path:
    raise FileNotFoundError("Azure CLI (az or az.cmd) not found in PATH.")

# List to store metrics data
metrics_data = []

# Metrics to collect
metrics = [
    "node_cpu_usage_percentage",
    "node_disk_usage_percentage"
]

# Time durations in hours
t_time_hour = [1, 24, 48]

# Step 1: Get all Azure subscription IDs
result = subprocess.run(
    [az_path, "account", "list", "--query", "[].id", "-o", "json"],
    capture_output=True, text=True
)

# Convert JSON string into a Python list
subscription_ids = json.loads(result.stdout)

# Step 2: Loop through each subscription
for sub_id in subscription_ids:
    print(f"\n=== Subscription: {sub_id} ===")

    # Set the current subscription
    subprocess.run([az_path, "account", "set", "--subscription", sub_id])

    # Get all AKS clusters in this subscription
    result = subprocess.run(
        [
            az_path, "resource", "list",
            "--resource-type", "Microsoft.ContainerService/managedClusters",
            "--query", "[].{name:name, resourceGroup:resourceGroup}",
            "-o", "json"
        ],
        capture_output=True, text=True
    )

    # Convert JSON string to Python list of dictionaries
    try:
        aks_clusters = json.loads(result.stdout)
        for cluster in aks_clusters:
            cluster["SubscriptionId"] = sub_id  # Add subscription ID
            print(f"\n=================== AKS Cluster: {cluster['name']} ============================")

            # Step 3: Collect metrics for each AKS cluster
            resource = f"/subscriptions/{sub_id}/resourceGroups/{cluster['resourceGroup']}/providers/Microsoft.ContainerService/managedClusters/{cluster['name']}"

            for t_time in t_time_hour:
                print(f"\n------ Time Duration: Last {t_time} hours -------")
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(hours=t_time)
                start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

                for metric in metrics:
                    cmd = [
                        az_path, "monitor", "metrics", "list",
                        "--resource", resource,
                        "--metric", metric,
                        "--aggregation", "Average",
                        "--interval", "PT1H",
                        "--start-time", start_time_str,
                        "--end-time", end_time_str,
                        "--query", ("value[0].{"
                                    "timestamp:timeseries[0].data[-1].timeStamp, "
                                    "name:name.localizedValue, "
                                    "average:timeseries[0].data[-1].average, "
                                    "unit:unit}"),
                        "--output", "json"
                    ]

                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                        metric_data = json.loads(result.stdout)
                        # Debugging: Print the raw metric data to verify
                        print(f"Debug - Metric Data for {metric}: {metric_data}")
                        metric_name = metric_data.get("name", metric)  # Fallback to metric ID if localizedValue is missing
                        metrics_data.append({
                            "Subscription ID": sub_id,
                            "Resource Group": cluster["resourceGroup"],
                            "Resource Name": cluster["name"],
                            "Metric": metric_name,
                            "Time Duration (Hours)": t_time,
                            "Timestamp": metric_data.get("timestamp", "N/A"),
                            "Average Value": metric_data.get("average", "N/A"),
                            "Unit": metric_data.get("unit", "N/A")
                        })
                    except subprocess.CalledProcessError as e:
                        print(f"\n--- Error retrieving metric '{metric}' for {cluster['name']} ---\n{e.stderr.strip()}")
                        metrics_data.append({
                            "Subscription ID": sub_id,
                            "Resource Group": cluster["resourceGroup"],
                            "Resource Name": cluster["name"],
                            "Metric": metric,
                            "Time Duration (Hours)": t_time,
                            "Timestamp": "N/A",
                            "Average Value": "Error",
                            "Unit": "N/A"
                        })
                    except json.JSONDecodeError:
                        print(f"\n--- Error parsing JSON for metric '{metric}' for {cluster['name']} ---")
                        metrics_data.append({
                            "Subscription ID": sub_id,
                            "Resource Group": cluster["resourceGroup"],
                            "Resource Name": cluster["name"],
                            "Metric": metric,
                            "Time Duration (Hours)": t_time,
                            "Timestamp": "N/A",
                            "Average Value": "JSON Error",
                            "Unit": "N/A"
                        })

    except json.JSONDecodeError:
        print(f"Could not read AKS cluster data as JSON for subscription {sub_id}.")

# Step 4: Create a DataFrame and save to Excel with improved formatting
df = pd.DataFrame(metrics_data)
excel_file = "aks_cluster_metrics.xlsx"

# Save to Excel with styled headers
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name="AKS Cluster Metrics", index=False)
    worksheet = writer.sheets["AKS Cluster Metrics"]
    for cell in worksheet["1:1"]:  # Bold the header row
        cell.font = cell.font.copy(bold=True)
    for column_cells in worksheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells if cell.value)
        worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

print(f"\nData exported to {excel_file}")
