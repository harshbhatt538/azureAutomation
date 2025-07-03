import subprocess
import json
import shutil
from datetime import datetime, timedelta, timezone
import pandas as pd
import openpyxl

# Find Azure CLI executable
az_path = shutil.which("az") or shutil.which("az.cmd")
if not az_path:
    raise FileNotFoundError("Azure CLI (az or az.cmd) not found in PATH.")

# Hardcoded lists
subscription_ids = ["301aa305-3920-4dd7-815a-57fd05b362fe"]
resource_groups = ["rgforvm"]
redis_names = ["redis-1-test"]

# List to store metrics data
metrics_data = []

# Metrics to collect with their configurations
metrics = [
    {"name": "UsedMemory", "aggregation": "Maximum", "query": "value[0].timeseries[0].data[].[timeStamp, maximum]", "post_process": True},
    {"name": "ServerLoad", "aggregation": "Maximum", "query": "value[0].timeseries[0].data[].[timeStamp, maximum]", "post_process": True}
]

# Time duration (24 hours)
t_time_hour = 24

# Function to convert bytes to human-readable format
def bytes_to_human_readable(bytes_value):
    if bytes_value is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(bytes_value) < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} TB"

# Collect metrics for each Redis instance
for sub_id in subscription_ids:
    for rg in resource_groups:
        for redis_name in redis_names:
            print(f"\n=== Subscription: {sub_id}, Resource Group: {rg}, Redis: {redis_name} ===")

            # Construct resource ID
            resource = f"/subscriptions/{sub_id}/resourceGroups/{rg}/providers/Microsoft.Cache/Redis/{redis_name}"

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=t_time_hour)
            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

            for metric in metrics:
                print(f"\n------ Metric: {metric['name']} -------")
                cmd = [
                    az_path, "monitor", "metrics", "list",
                    "--resource", resource,
                    "--metric", metric["name"],
                    "--aggregation", metric["aggregation"],
                    "--interval", "PT1H",
                    "--start-time", start_time_str,
                    "--end-time", end_time_str,
                    "--query", metric["query"],
                    "--output", "json"
                ]

                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    print(f"Debug - Raw CLI Output for {metric['name']}: {result.stdout}")
                    metric_data = json.loads(result.stdout)

                    if "post_process" in metric:
                        data_points = metric_data
                        if data_points and len(data_points) > 0:
                            # Filter out None values and find the maximum
                            valid_data_points = [dp for dp in data_points if dp[1] is not None]
                            if valid_data_points:
                                max_value = max(dp[1] for dp in valid_data_points)
                                timestamp = next(dp[0] for dp in valid_data_points if dp[1] == max_value)
                                value = max_value
                                unit = "%" if metric["name"] == "ServerLoad" else "Human Readable"
                                if metric["name"] == "UsedMemory":
                                    value = bytes_to_human_readable(max_value)
                                entry = {
                                    "Subscription ID": sub_id,
                                    "Resource Group": rg,
                                    "Redis Name": redis_name,
                                    "Metric": metric["name"],
                                    "Time Duration (Hours)": t_time_hour,
                                    "Timestamp": timestamp,
                                    "Value": value,
                                    "Unit": unit
                                }
                                metrics_data.append(entry)
                                print(f"Debug - Appended {metric['name']} Entry: {entry}")
                            else:
                                metrics_data.append({
                                    "Subscription ID": sub_id,
                                    "Resource Group": rg,
                                    "Redis Name": redis_name,
                                    "Metric": metric["name"],
                                    "Time Duration (Hours)": t_time_hour,
                                    "Timestamp": "N/A",
                                    "Value": "N/A",
                                    "Unit": "%" if metric["name"] == "ServerLoad" else "Human Readable"
                                })
                        else:
                            metrics_data.append({
                                "Subscription ID": sub_id,
                                "Resource Group": rg,
                                "Redis Name": redis_name,
                                "Metric": metric["name"],
                                "Time Duration (Hours)": t_time_hour,
                                "Timestamp": "N/A",
                                "Value": "N/A",
                                "Unit": "%" if metric["name"] == "ServerLoad" else "Human Readable"
                            })
                    else:
                        print(f"Debug - Unexpected metric data structure for {metric['name']}: {metric_data}")

                except subprocess.CalledProcessError as e:
                    print(f"\n--- Error retrieving metric '{metric['name']}' ---\n{e.stderr.strip()}")
                    metrics_data.append({
                        "Subscription ID": sub_id,
                        "Resource Group": rg,
                        "Redis Name": redis_name,
                        "Metric": metric["name"],
                        "Time Duration (Hours)": t_time_hour,
                        "Timestamp": "N/A",
                        "Value": "Error",
                        "Unit": "N/A"
                    })
                except json.JSONDecodeError:
                    print(f"\n--- Error parsing JSON for metric '{metric['name']}' ---\n{result.stdout}")
                    metrics_data.append({
                        "Subscription ID": sub_id,
                        "Resource Group": rg,
                        "Redis Name": redis_name,
                        "Metric": metric["name"],
                        "Time Duration (Hours)": t_time_hour,
                        "Timestamp": "N/A",
                        "Value": "JSON Error",
                        "Unit": "N/A"
                    })

# Create a DataFrame and save to Excel in a single sheet
df = pd.DataFrame(metrics_data)
excel_file = "redis_metrics.xlsx"

with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name="Metrics", index=False)
    worksheet = writer.sheets["Metrics"]
    # Bold the header row
    for cell in worksheet["1:1"]:
        cell.font = openpyxl.styles.Font(bold=True)
    # Auto-adjust column widths
    for column_cells in worksheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells if cell.value)
        worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

print(f"\nData exported to {excel_file}")