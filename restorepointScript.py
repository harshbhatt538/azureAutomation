#THE CODE FOR RESTOREPOINT

import subprocess
import json
import pandas as pd

# Lists of subscription IDs, resource groups, and collections
subscription_ids = ["301aa305-3920-4dd7-815a-57fd05b362fe"]  # Use unique subscription IDs
resource_groups = ["RGFORVM", "JASH"]  # Replace with your resource groups
collections = ["collection-1-rp", "Collectionrestorepoint"]  # Replace with your collection names

# List to store all restore point data
all_data = []

# Iterate over each subscription, resource group, and collection
for sub_id in subscription_ids:
    print(f"Processing subscription: {sub_id}")
    # Set the subscription context
    subprocess.run(f"az account set --subscription {sub_id}", shell=True, capture_output=True, text=True)
    
    for rg in resource_groups:
        for collection in collections:
            print(f"Fetching restore point for {sub_id}/{rg}/{collection}")
            # Run az command to get the latest restore point
            command = (
                f"az restore-point collection show --resource-group {rg} "
                f"--collection-name {collection} --restore-points "
                "--query 'restorePoints | sort_by(@, &timeCreated) | [-1]' -o json"
            )
            
            try:
                # Get command output
                result = subprocess.run(command, shell=True, text=True, capture_output=True, check=True)
                data = json.loads(result.stdout)

                # Get disk names
                disks = []
                os_disk = data.get("sourceMetadata", {}).get("storageProfile", {}).get("osDisk", {}).get("name")
                if os_disk:
                    disks.append(os_disk)
                for disk in data.get("sourceMetadata", {}).get("storageProfile", {}).get("dataDisks", []):
                    if disk.get("name"):
                        disks.append(disk["name"])

                # Prepare data for Excel
                excel_data = {
                    "Subscription ID": sub_id,
                    "Resource Group": rg,
                    "Collection Name": collection,
                    "Restore Point Name": data.get("name", "N/A"),
                    "Disks": ", ".join(disks) if disks else "None",
                    "Creation Time": data.get("timeCreated", "N/A"),
                    "Provisioning State": data.get("provisioningState", "N/A")
                }
                print(f"Adding data: {excel_data}")
                all_data.append(excel_data)
            
            except subprocess.CalledProcessError as e:
                print(f"No restore points found for {sub_id}/{rg}/{collection}: {e.stderr}")
            except json.JSONDecodeError:
                print(f"Failed to parse JSON for {sub_id}/{rg}/{collection}")
            except Exception as e:
                print(f"Error for {sub_id}/{rg}/{collection}: {str(e)}")

# Write data to Excel
if all_data:
    print(f"Total records to write: {len(all_data)}")
    final_df = pd.DataFrame(all_data)
    output_file = "restore_points3.xlsx"
    final_df.to_excel(output_file, index=False, engine="openpyxl")
    print(f"Data written to '{output_file}'!")
else:
    print("No data to write to Excel.")
