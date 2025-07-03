from azure.identity import DefaultAzureCredential
from azure.monitor.query import MetricsQueryClient
from azure.mgmt.eventhub import EventHubManagementClient
from datetime import datetime, timedelta
import pytz
import pandas as pd
from prophet import Prophet
import matplotlib.pyplot as plt

# Authenticate
credential = DefaultAzureCredential()
client = MetricsQueryClient(credential)

# Use your actual Event Hub Namespace resource URI and subscription ID
resource_uri = "/subscriptions/301aa305-3920-4dd7-815a-57fd05b362fe/resourceGroups/vm-1_group/providers/Microsoft.EventHub/namespaces/EhNa-hb-1"
subscription_id = "301aa305-3920-4dd7-815a-57fd05b362fe"  # Extracted from resource_uri

# Initialize EventHubManagementClient to list event hubs
eventhub_client = EventHubManagementClient(credential, subscription_id)

# Define the time range (last 7 days for data collection) in IST
ist = pytz.timezone('Asia/Kolkata')
end_time = datetime.now(ist)
start_time = end_time - timedelta(days=7)

# Dynamically get all event hubs in the namespace
namespace_name = resource_uri.split("/")[-1]  # Extract namespace name 
resource_group_name = resource_uri.split("/")[4]  # Extract resource group 

eventhubs = eventhub_client.event_hubs.list_by_namespace(resource_group_name, namespace_name)
eventhub_names = [eh.name for eh in eventhubs]

# Build dynamic filter
if eventhub_names:
    filter_parts = [f"EntityName eq '{name}'" for name in eventhub_names]
    dynamic_filter = " or ".join(filter_parts)
else:
    dynamic_filter = "EntityName eq ''"  # Fallback if no event hubs are found

# 1. Define the metric names list at the top (after other variables)
metric_names_list = ["IncomingMessages", "OutgoingMessages"]

# Query the 'IncomingMessages' metric with dynamic filter
try:
    # 2. Replace the single query with a loop over metric_names_list
    data_by_entity = {}

    for metric_name in metric_names_list:
        response = client.query_resource(
            resource_uri=resource_uri,
            metric_names=[metric_name],
            timespan=(start_time, end_time),
            granularity="PT5M",
            aggregations=["Total"],
            filter=dynamic_filter
        )

        for metric in response.metrics:
            for time_series in metric.timeseries:
                entity_name = time_series.metadata_values.get('EntityName', 'N/A')
                key = (entity_name, metric_name)  # Use tuple as key
                if key not in data_by_entity:
                    data_by_entity[key] = []
                for data_point in time_series.data:
                    data_by_entity[key].append({
                        'ds': data_point.timestamp,
                        'y': data_point.total or 0,
                        'metric_name': metric_name
                    })

    # Convert each entity's data to a separate DataFrame and store in variables
    entity_dfs = {}
    for (entity_name, metric_name), data in data_by_entity.items():
        df = pd.DataFrame(data)
        df['ds'] = pd.to_datetime(df['ds']).dt.tz_convert(ist).dt.tz_localize(None)
        entity_dfs[(entity_name, metric_name)] = df
        if df.empty:
            print(f"\nNo data for {entity_name} - {metric_name}")
        else:
            print(f"\nDataFrame for {entity_name} - {metric_name} stored in variable: df_{entity_name.replace('-', '_')}_{metric_name}")
            print(df)

except Exception as e:
    print(f"Error querying metrics: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Prophet modeling and anomaly detection for each event hub dynamically, with single Excel sheet
output_file = "anomaly_detection_results.xlsx"
all_anomalies = []  # List to collect all anomaly data
anomaly_start_time = (end_time - timedelta(hours=24)).replace(tzinfo=None)  # Last 24 hours for anomaly detection in IST

with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
    for (entity_name, metric_name), df in entity_dfs.items():
        if not df.empty:  # Ensure the DataFrame has data
            # Step 3: Prophet model (using 7 days of data)
            model = Prophet(weekly_seasonality=True, daily_seasonality=False, interval_width=0.80)  # Tightened interval to 80%
            model.fit(df[['ds', 'y']])

            # Step 4: Forecast (using 7 days of data)
            future = model.make_future_dataframe(periods=0, freq='5min')  # Match granularity
            forecast = model.predict(future)

            # Merge predictions
            df_merged = df.merge(forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']], on='ds', how='left')

            # Filter for last 24 hours for anomaly detection
            df_last_24h = df_merged[df_merged['ds'] >= anomaly_start_time].copy()  # Use .copy() to avoid SettingWithCopyWarning

            # Step 5: Anomaly detection with bifurcation (only for last 24 hours)
            df_last_24h.loc[:, 'anomaly'] = (df_last_24h['y'] > df_last_24h['yhat_upper']) | (df_last_24h['y'] < df_last_24h['yhat_lower'])
            spikes = df_last_24h[df_last_24h['y'] > df_last_24h['yhat_upper']]
            drops = df_last_24h[df_last_24h['y'] < df_last_24h['yhat_lower']]

            # Prepare anomaly data for this event hub and metric
            if not spikes.empty:
                spikes_df = spikes.assign(Anomaly_Type='Spike', Event_Hub=entity_name, Metric_Name=metric_name)
                all_anomalies.append(spikes_df)
            else:
                # Add a row for "No spikes found"
                all_anomalies.append(pd.DataFrame([{
                    'ds': None,
                    'y': None,
                    'yhat': None,
                    'yhat_lower': None,
                    'yhat_upper': None,
                    'Anomaly_Type': 'Spike',
                    'Event_Hub': entity_name,
                    'Metric_Name': metric_name,
                    'Note': 'No spikes found'
                }]))
            if not drops.empty:
                drops_df = drops.assign(Anomaly_Type='Drop', Event_Hub=entity_name, Metric_Name=metric_name)
                all_anomalies.append(drops_df)
            else:
                # Add a row for "No drops found"
                all_anomalies.append(pd.DataFrame([{
                    'ds': None,
                    'y': None,
                    'yhat': None,
                    'yhat_lower': None,
                    'yhat_upper': None,
                    'Anomaly_Type': 'Drop',
                    'Event_Hub': entity_name,
                    'Metric_Name': metric_name,
                    'Note': 'No drops found'
                }]))

            # Print debug for anomalies with explicit messaging (last 24 hours only) and some diagnostics
            print(f"\nAnomalies for {entity_name} (last 24 hours, from {anomaly_start_time} to {end_time.replace(tzinfo=None)}):")
            print(f"Sample last 24h data: \n{df_last_24h[['ds', 'y', 'yhat', 'yhat_lower', 'yhat_upper']].head()}")
            if not spikes.empty:
                print("\nSpikes:")
                print(spikes[['ds', 'y', 'yhat', 'yhat_lower', 'yhat_upper']])
            else:
                print("\nSpikes: No spikes found")
            if not drops.empty:
                print("\nDrops:")
                print(drops[['ds', 'y', 'yhat', 'yhat_lower', 'yhat_upper']])
            else:
                print("\nDrops: No drops found")

            # Visualization for each event hub
            # plt.figure(figsize=(15, 6))
            # plt.plot(df_merged['ds'], df_merged['y'], label='Actual', color='blue')
            # plt.plot(df_merged['ds'], df_merged['yhat'], label='Predicted', color='green')
            # plt.fill_between(df_merged['ds'], df_merged['yhat_lower'], df_merged['yhat_upper'], color='gray', alpha=0.2)
            # plt.scatter(df_last_24h[df_last_24h['anomaly']]['ds'], df_last_24h[df_last_24h['anomaly']]['y'],
            #             color='red', label='Anomaly', zorder=10)
            # plt.title(f'Anomaly Detection for {entity_name}')
            # plt.xlabel('Time (IST)')
            # plt.ylabel('Messages')
            # plt.legend()
            # plt.grid(True)
            # plt.tight_layout()
            # plt.show()

    # 5. Add 'Metric_Name' to the Excel output columns
    if all_anomalies:
        combined_anomalies = pd.concat(all_anomalies, ignore_index=True)
        combined_anomalies = combined_anomalies.rename(columns={
            'ds': 'Timestamp (IST)',
            'y': 'Actual Value',
            'yhat': 'Predicted Value',
            'yhat_lower': 'Lower Bound',
            'yhat_upper': 'Upper Bound',
            'Metric_Name': 'Metric Name',
            'Note': 'Note'
        })
        # Ensure 'Metric Name' is in the output
        combined_anomalies = combined_anomalies.sort_values(['Event_Hub', 'Metric Name', 'Timestamp (IST)'])
        combined_anomalies.to_excel(writer, sheet_name="Anomalies", index=False)
        # Add formatting with xlsxwriter
        workbook = writer.book
        worksheet = writer.sheets["Anomalies"]
        header_format = workbook.add_format({'bold': True, 'bg_color': '#C6E0B4', 'border': 1})
        for col_num, value in enumerate(combined_anomalies.columns.values):
            worksheet.write(0, col_num, value, header_format)
    else:
        # Write a sheet indicating no anomalies across all event hubs in the last 24 hours
        df_no_anomalies = pd.DataFrame({
            'Message': ['No anomalies (spikes or drops) detected across all event hubs in the last 24 hours']
        })
        df_no_anomalies.to_excel(writer, sheet_name="Anomalies", index=False)

