from azure.mgmt.containerservice import ContainerServiceClient
from azure.identity import ClientSecretCredential
import os
from dotenv import load_dotenv
from kubernetes import client, config

load_dotenv()
subscription_id = '835997e0-c4d9-42d8-ac2f-9794364d5e0e'



credential = ClientSecretCredential(
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET")
)
aks_client = ContainerServiceClient(credential, subscription_id)

for cluster in aks_client.managed_clusters.list():
    
    cluster_name = cluster.name
    resource_group = cluster.id.split("/")[4]
    print(f"cluster name:{cluster_name}")
    print(f"resource_group name:{resource_group}")
    # Get AKS cluster info
    cluster = aks_client.managed_clusters.get(resource_group, cluster_name)
    print(f"Cluster Provisioning State: {cluster.provisioning_state}")
    print(f"Kubernetes Version: {cluster.kubernetes_version}")

    # Get AKS credentials programmatically
    print("\n Fetching kubeconfig for AKS...")
    credentials = aks_client.managed_clusters.list_cluster_user_credentials(resource_group, cluster_name)
    kubeconfig = credentials.kubeconfigs[0].value.decode("utf-8")

    # Save kubeconfig to a temporary file
    kubeconfig_path = os.path.expanduser("~/.kube/config")
    os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)
    with open(kubeconfig_path, "w") as f:
        f.write(kubeconfig)

    # Load kubeconfig
    print("\n Checking pod and node statuses...")
    config.load_kube_config()

    # Create API clients
    core_v1 = client.CoreV1Api()

    # List node statuses
    print("\n Node Statuses:")
    nodes = core_v1.list_node()
    a = 0
    b = 0
    c = 0
    for node in nodes.items:
        print(f"Node Name: {node.metadata.name}, Status: {node.status.conditions[-1].type}")
        if node.status.conditions[-1].type == "Ready":
            a=a+1

        elif node.status.condition[-1].type == "Not Ready":
            b=b+1

        elif node.status.condition[-1].type == "Unknown":
            c=c+1

    print(f"number of Ready nodes = {a}") 
    print(f"number of Not Ready nodes = {b}") 
    print(f"number of Unknown nodes = {c}") 

    # List pod statuses across all namespaces
    print("\n Pod Statuses:")
    pods = core_v1.list_pod_for_all_namespaces()
    a=0
    b=0
    c=0
    d=0
    e=0
    for pod in pods.items:
        print(f"Namespace: {pod.metadata.namespace}, Pod: {pod.metadata.name}, Status: {pod.status.phase}")
        if pod.status.phase == "Running" :
            a=a+1
        
        elif pod.status.phase == "Failed":
            print(f"Namespace: {pod.metadata.namespace}, Pod: {pod.metadata.name}, Status: {pod.status.phase}")
            b=b+1

        elif pod.status.phase == "Pending":
            print(f"Namespace: {pod.metadata.namespace}, Pod: {pod.metadata.name}, Status: {pod.status.phase}")
            c=c+1
        
        elif pod.status.phase == "Succeeded":
            print(f"Namespace: {pod.metadata.namespace}, Pod: {pod.metadata.name}, Status: {pod.status.phase}")
            d=d+1
        
        elif pod.status.phase == "Unknown":
            print(f"Namespace: {pod.metadata.namespace}, Pod: {pod.metadata.name}, Status: {pod.status.phase}")
            e=e+1

    print(f"number of Running pods = {a}")
    print(f"number of Failed pods = {b}")
    print(f"number of Pending pods = {c}")
    print(f"number of Succeeded pods = {d}")
    print(f"number of Unknown pods = {e}")
    print("=======================================================================================")
    print("=======================================================================================")


print("AKS Clusters found:")
listofcluster= []
for cluster in aks_client.managed_clusters.list():
    print(f"- {cluster.name}")
    
    listofcluster.append(cluster.name)   

print(listofcluster) 

