import json
import boto3
import os 

def lambda_handler(event, context):
    
    dynamodb_resource = boto3.resource('dynamodb')
    table_name =  os.environ['RUNNING_TABLE_NAME']

    # print(event)
    # taskArn = event['taskArn'] # incorrect key/format
    # taskArn = event['detail'][0]['taskArn'] # also incorrect key/format
    
    taskArn = event['detail']['taskArn']
    
    table = dynamodb_resource.Table(table_name)
    
    response = table.delete_item(Key = {'taskArn': taskArn})

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
