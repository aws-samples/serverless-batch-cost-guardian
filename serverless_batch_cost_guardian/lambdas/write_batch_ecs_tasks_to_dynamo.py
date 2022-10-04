import json
import boto3
from decimal import Decimal
import os

batch_client = boto3.client('batch')
ecs_client = boto3.client('ecs')
dynamodb_resource = boto3.resource('dynamodb')
running_table_name = os.environ['RUNNING_TABLE_NAME'] 
aggregate_table_name = os.environ['AGGREGATE_TABLE_NAME']
running_table = dynamodb_resource.Table(running_table_name)
aggregate_table = dynamodb_resource.Table(aggregate_table_name)

def lambda_handler(event, context):
    
    response = batch_client.describe_compute_environments(
        computeEnvironments=[
            os.environ['BATCH_COMPUTE_ENV_NAME']
        ]
    )
    
    # Stack overflow help: https://stackoverflow.com/questions/23306653/python-accessing-nested-json-data 
    ecs_cluster_arn = response['computeEnvironments'][0]['ecsClusterArn']
    
    # Help: https://www.simplifiedpython.net/python-split-string-by-character/ 
    ecs_cluster_name = ecs_cluster_arn.split('/')[1]

    response = ecs_client.list_tasks(
        cluster=ecs_cluster_name
    )
    
    total_cpu = 0
    total_memory = 0
    
    for taskArn in response['taskArns']: 
            response = ecs_client.describe_tasks(
                cluster=ecs_cluster_name,
                tasks=[
                    taskArn,
                ]
            )
            task_id = response['tasks'][0]['taskArn']
            task_cpu_units = response['tasks'][0]['cpu']
            task_cpu_count = int(task_cpu_units)/1024
            task_memory_mib = response['tasks'][0]['memory']
            task_memory_gb = int(task_memory_mib)/1024
            print(task_id)
            print(task_cpu_count)
            print(task_memory_gb)
            total_cpu = total_cpu + task_cpu_count
            total_memory = total_memory + task_memory_gb
            # DDB put item here
            # table name: batch_ecs_running_tasks_table
            # pk: taskArn
            response = running_table.put_item(
            Item = { 
                 'taskArn': task_id,
                 'taskCpuCount': str(task_cpu_count),
                 'taskMemoryGb': str(task_memory_gb)
                   }
            )
            print(response)
    
    response = aggregate_table.put_item(
    Item = { 
        'aggregate_key': "aggregate_key",
        'totalCpu': Decimal(total_cpu),
        'totalMemory': Decimal(total_memory)
        }
    )
    print(response)
    
    return {
        'statusCode': 200,
        "startTime": event['startTime'],
        "startCost": event['startCost'],
        "budgetLimit": event['budgetLimit'],
        'budgetMet': 'NO'
    }