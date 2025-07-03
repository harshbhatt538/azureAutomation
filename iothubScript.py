import subprocess
import json
import shutil
from datetime import datetime, timedelta, timezone
import pandas as pd

# Find Azure CLI executable
az_path = shutil.which("az") or shutil.which("az.cmd")
if not az_path:
    raise FileNotFoundError("Azure CLI (az or az.cmd) not found in PATH.")

# List to store all IoT Hub info and metrics
all_iothubs = []
metrics_data = []

# Metrics to collect
metrics = [
    "connectedDeviceCount",
    "totalDeviceCount",
    "dailyMessageQuotaUsed",
    "d2c.telemetry.ingress.allProtocol"
]

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

    # Get IoT Hubs in this subscription
    result = subprocess.run(
        [
            az_path, "resource", "list",
            "--resource-type", "Microsoft.Devices/IotHubs",
            "--query", "[].{IoTHubName:name, ResourceGroup:resourceGroup}",
            "-o", "json"
        ],
        capture_output=True, text=True
    )

    # Convert JSON string to Python list of dictionaries
    try:
        iothubs = json.loads(result.stdout)
        for hub in iothubs:
            hub["SubscriptionId"] = sub_id  # Add subscription ID
        all_iothubs.extend(iothubs)  # Add to the full list
    except json.JSONDecodeError:
        print("Could not read IoT Hub data as JSON.")

# Step 3: Collect metrics for each IoT Hub
for hub in all_iothubs:
    resource = f"/subscriptions/{hub['SubscriptionId']}/resourceGroups/{hub['ResourceGroup']}/providers/Microsoft.Devices/IotHubs/{hub['IoTHubName']}"
    interval = "PT1M"
    aggregation = "Average"
    output_format = "json"  # Use JSON for parsing

    print(f"\n=================== IoT Hub: {hub['IoTHubName']} ============================")

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
                "--interval", interval,
                "--aggregation", aggregation,
                "--start-time", start_time_str,
                "--end-time", end_time_str,
                "--query", ("value[0].{"
                            "timestamp:timeseries[0].data[-1].timeStamp, "
                            "name:name.localizedValue, "
                            "average:timeseries[0].data[-1].average}"),
                "--output", output_format
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                metric_data = json.loads(result.stdout)
                # Debugging: Print the raw metric data to verify
                print(f"Debug - Metric Data for {metric}: {metric_data}")
                metric_name = metric_data.get("name", metric)  # Fallback to metric ID if localizedValue is missing
                metrics_data.append({
                    "Subscription ID": hub["SubscriptionId"],
                    "Resource Group": hub["ResourceGroup"],
                    "IoT Hub Name": hub["IoTHubName"],
                    "Metric": metric_name,
                    "Time Duration (Hours)": t_time,
                    "Timestamp": metric_data.get("timestamp", "N/A"),
                    "Average Value": metric_data.get("average", "N/A")
                })
            except subprocess.CalledProcessError as e:
                print(f"\n--- Error retrieving metric '{metric}' for {hub['IoTHubName']} ---\n{e.stderr.strip()}")
                metrics_data.append({
                    "Subscription ID": hub["SubscriptionId"],
                    "Resource Group": hub["ResourceGroup"],
                    "IoT Hub Name": hub["IoTHubName"],
                    "Metric": metric,
                    "Time Duration (Hours)": t_time,
                    "Timestamp": "N/A",
                    "Average Value": "Error"
                })
            except json.JSONDecodeError:
                print(f"\n--- Error parsing JSON for metric '{metric}' for {hub['IoTHubName']} ---")
                metrics_data.append({
                    "Subscription ID": hub["SubscriptionId"],
                    "Resource Group": hub["ResourceGroup"],
                    "IoT Hub Name": hub["IoTHubName"],
                    "Metric": metric,
                    "Time Duration (Hours)": t_time,
                    "Timestamp": "N/A",
                    "Average Value": "JSON Error"
                })

# Step 4: Create a DataFrame and save to Excel with improved formatting
df = pd.DataFrame(metrics_data)
excel_file = "iot_hub_metrics.xlsx"

# Save to Excel with styled headers
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name="IoT Hub Metrics", index=False)
    worksheet = writer.sheets["IoT Hub Metrics"]
    for cell in worksheet["1:1"]:  # Bold the header row
        cell.font = cell.font.copy(bold=True)  # Suppress DeprecationWarning by using a modern approach if needed
    for column_cells in worksheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells if cell.value)
        worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

print(f"\nData exported to {excel_file}")
