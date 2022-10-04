import json
import boto3
import datetime
from decimal import Decimal
import os

# run these environment variable seetings on cold start (outside handler) only since they are static
dynamodb_resource = boto3.resource('dynamodb')
aggregate_table_name = os.environ['AGGREGATE_TABLE_NAME']
latest_timestamp_running_cost_table_name = os.environ['LATEST_TIMESTAMP_RUNNING_COST_TABLE_NAME']
aggregate_table = dynamodb_resource.Table(aggregate_table_name)
latest_timestamp_running_cost_table = dynamodb_resource.Table(latest_timestamp_running_cost_table_name)

def lambda_handler(event, context):
    
    response = aggregate_table.get_item(Key={
      "aggregate_key": "aggregate_key"
    })
    
    total_cpu = response["Item"]["totalCpu"]
    total_memory = response["Item"]["totalMemory"]
    
    budget_limit = float(event["budgetLimit"])

    # initialize a DDB with start_time in previous step SFN and get item here
    response = latest_timestamp_running_cost_table.get_item(Key={
      "partition-key": "pk"
    }) 
    last_timestamp_str = response["Item"]["latestTimeStamp"]
    
    # initialize a DDB with start_cost in previous step SFN and get item here 
    running_cost = response["Item"]["runningCost"]
    
    time_now = datetime.datetime.now()
    last_timestamp = datetime.datetime.strptime(last_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
    
    time_delta = time_now - last_timestamp
    time_since_last_poll = get_hours(time_delta)
    current_cpu_cost = time_since_last_poll * float(total_cpu) * 0.04048 # TODO: Leverage AWS Price List API Query with boto3 to avoid hardcoding in price
    current_memory_cost = time_since_last_poll * float(total_memory) * 0.004445 # TODO: Leverage AWS Price List API Query with boto3 to avoid hardcoding in price
    
    current_cost = float(running_cost) + current_cpu_cost + current_memory_cost
    
    if (current_cost > budget_limit):
        # nuke remaining jobs
        return {
            'budgetMet': 'YES',
            'budgetLimit': budget_limit
        }
        
    # update item running cost to DDB with new current cost value
    # update item last timestamp to DDB with new datetime now
    response = latest_timestamp_running_cost_table.update_item(
    Key={
        'partition-key': "pk"
    },
    UpdateExpression='set latestTimeStamp = :time_now, runningCost = :current_cost',
        ExpressionAttributeValues={
            ':current_cost': Decimal(str(current_cost)),
            ':time_now': str(time_now)
        }    
    )
    
    return {
        'statusCode': 200,
        'budgetLimit': budget_limit,
        'budgetMet': 'NO'
    }

def get_hours(time):
    duration_in_s = time.total_seconds()
    old_result = divmod(duration_in_s, 3600)[0]
    result = float(duration_in_s)/3600
    return (result)