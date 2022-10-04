import json
import boto3
from decimal import Decimal
import os

dynamodb_resource = boto3.resource('dynamodb')
aggregate_table_name = os.environ['AGGREGATE_TABLE_NAME']
aggregate_table = dynamodb_resource.Table(aggregate_table_name)

def lambda_handler(event, context):
    
    total_deleted_cpu = 0
    total_deleted_memory = 0
    
    for record in event["Records"]:
        
        if record['eventName'] == 'REMOVE':
            old_record = record['dynamodb']['OldImage']
            print(f"{old_record} was deleted")
            
            # subtract removed from aggregate
            deleted_cpu_str = old_record['taskCpuCount']['S']
            deleted_memory_str = old_record['taskMemoryGb']['S']
            print(deleted_cpu_str)
            print(deleted_memory_str)
            deleted_cpu = float(deleted_cpu_str)
            deleted_memory = float(deleted_memory_str)
            total_deleted_cpu = total_deleted_cpu + deleted_cpu
            total_deleted_memory = total_deleted_memory + deleted_memory
            
    # update item, not put item
    response = aggregate_table.update_item(
    Key={
        'aggregate_key': "aggregate_key"
    },
    UpdateExpression='set totalCpu = totalCpu - :decrement_cpu, totalMemory = totalMemory - :decrement_memory',
        ExpressionAttributeValues={
            ':decrement_cpu': Decimal(total_deleted_cpu),
            ':decrement_memory': Decimal(total_deleted_memory)
        }    
    )
    print(response)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
