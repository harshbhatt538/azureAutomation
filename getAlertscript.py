#THE CODE FOR CHECKLIST OF MONITOR


import subprocess
import json
import re
from datetime import datetime, timedelta, timezone
from openpyxl import Workbook

def get_subscription_id():
    cmd = ["az", "account", "show", "--query", "id", "--output", "tsv"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()

def parse_azure_time(timestamp_str):
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1] + "+00:00"
    match = re.match(r"^(.*\.\d{6})\d*(\+\d{2}:\d{2})$", timestamp_str)
    if match:
        timestamp_str = match.group(1) + match.group(2)
    return datetime.fromisoformat(timestamp_str)

def get_fired_alerts(start_time=None, end_time=None):
    try:
        if not end_time:
            end_time = datetime.now(timezone.utc)
        if not start_time:
            start_time = end_time - timedelta(hours=1)

        print(f"Getting alerts from {start_time.isoformat()} to {end_time.isoformat()}...\n")

        sub_id = get_subscription_id()
        url = (
            f"https://management.azure.com/subscriptions/{sub_id}/"
            f"providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview"
        )

        cmd = ["az", "rest", "--method", "get", "--url", url]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        alerts_data = json.loads(result.stdout)
        alerts = alerts_data.get("value", [])

        # Create a new workbook every time (not append)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Fired Alerts"

        # Write header row
        sheet.append(["Name", "Alert Condition", "Fire Time"])

        count = 0
        for alert in alerts:
            props = alert.get("properties", {})
            essentials = props.get("essentials", {})
            fire_time_str = essentials.get("startDateTime")
            if not fire_time_str:
                continue

            try:
                fire_time = parse_azure_time(fire_time_str)
            except Exception:
                print(f"Skipping invalid timestamp: {fire_time_str}")
                continue

            if (
                start_time <= fire_time <= end_time and
                essentials.get("monitorCondition") == "Fired" and
                essentials.get("alertState") == "New"
            ):
                count += 1
                name = essentials.get("alertRule")
                condition = essentials.get("monitorCondition")

                #  Convert fire_time to IST (UTC+5:30)
                fire_time_ist = fire_time.astimezone(timezone(timedelta(hours=5, minutes=30)))
                time_str = fire_time_ist.strftime("%Y-%m-%d %H:%M:%S")

                sheet.append([name, condition, time_str])

                print("\n======================")
                print(f"Name: {name}")
                print(f"Alert Condition: {condition}")
                print(f"Fire Time (IST): {time_str}")
                print("======================")

        # Save (overwrite) file
        workbook.save("fired_alerts2.xlsx")
        print(f"\n Excel file 'fired_alerts.xlsx' saved with {count} alert(s).")

        if count == 0:
            print("No fired alerts found in the given time range.")

    except subprocess.CalledProcessError as e:
        print("Error calling Azure CLI or REST API:\n", e.stderr)
    except Exception as e:
        print("Unexpected error:\n", str(e))

if __name__ == "__main__":
    get_fired_alerts()


 
