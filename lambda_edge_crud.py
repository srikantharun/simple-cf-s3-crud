"""
Lambda@Edge function for handling CRUD operations with S3 backend
This function runs on Origin Request events in CloudFront
"""

import json
import boto3
import uuid
import os
from datetime import datetime
from urllib.parse import parse_qs, unquote

s3_client = boto3.client('s3')
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '')

def generate_id():
    """Generate a unique ID for new items"""
    return str(uuid.uuid4())

def parse_path(path):
    """
    Parse the request path to extract collection and item ID
    Examples:
      /items -> collection='items', item_id=None
      /items/123 -> collection='items', item_id='123'
      /products/food/beverages -> collection='products/food/beverages', item_id=None
      /products/food/beverages/abc -> collection='products/food/beverages', item_id='abc'
    """
    path = path.strip('/')
    if not path:
        return None, None

    parts = path.split('/')

    # If last part looks like an ID (contains hyphens or is UUID-like), treat it as item_id
    # Otherwise, entire path is the collection
    if len(parts) > 1:
        # Check if last part might be an ID
        last_part = parts[-1]
        if '-' in last_part or len(last_part) == 36:  # Likely a UUID or ID
            collection = '/'.join(parts[:-1])
            item_id = last_part
        else:
            collection = path
            item_id = None
    else:
        collection = path
        item_id = None

    return collection, item_id

def get_s3_key(collection, item_id=None):
    """Generate S3 key for storing items"""
    if item_id:
        return f"{collection}/{item_id}.json"
    else:
        return f"{collection}/"

def list_items_in_collection(collection):
    """List all items in a collection"""
    try:
        prefix = f"{collection}/"
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=prefix,
            Delimiter='/'
        )

        items = []
        if 'Contents' in response:
            for obj in response['Contents']:
                # Skip the folder marker
                if obj['Key'].endswith('.json'):
                    try:
                        # Get the item content
                        obj_response = s3_client.get_object(
                            Bucket=BUCKET_NAME,
                            Key=obj['Key']
                        )
                        item_data = json.loads(obj_response['Body'].read().decode('utf-8'))
                        items.append(item_data)
                    except Exception as e:
                        print(f"Error reading {obj['Key']}: {str(e)}")
                        continue

        return items
    except Exception as e:
        print(f"Error listing items: {str(e)}")
        return []

def get_item(collection, item_id):
    """Get a specific item from S3"""
    try:
        key = get_s3_key(collection, item_id)
        response = s3_client.get_object(
            Bucket=BUCKET_NAME,
            Key=key
        )
        item_data = json.loads(response['Body'].read().decode('utf-8'))
        return item_data
    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"Error getting item: {str(e)}")
        raise

def put_item(collection, item_id, data):
    """Store an item in S3"""
    try:
        key = get_s3_key(collection, item_id)

        # Add metadata
        if 'id' not in data:
            data['id'] = item_id
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow().isoformat() + 'Z'
        data['updated_at'] = datetime.utcnow().isoformat() + 'Z'

        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        return data
    except Exception as e:
        print(f"Error putting item: {str(e)}")
        raise

def delete_item(collection, item_id):
    """Delete a specific item from S3"""
    try:
        key = get_s3_key(collection, item_id)
        s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=key
        )
        return True
    except Exception as e:
        print(f"Error deleting item: {str(e)}")
        raise

def delete_all_items(collection):
    """Delete all items in a collection"""
    try:
        prefix = f"{collection}/"
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=prefix
        )

        if 'Contents' in response:
            for obj in response['Contents']:
                s3_client.delete_object(
                    Bucket=BUCKET_NAME,
                    Key=obj['Key']
                )
        return True
    except Exception as e:
        print(f"Error deleting all items: {str(e)}")
        raise

def create_response(status_code, body, headers=None):
    """Create a CloudFront response"""
    default_headers = {
        'content-type': [{'key': 'Content-Type', 'value': 'application/json'}],
        'access-control-allow-origin': [{'key': 'Access-Control-Allow-Origin', 'value': '*'}],
        'access-control-allow-methods': [{'key': 'Access-Control-Allow-Methods', 'value': 'GET, POST, PUT, PATCH, DELETE, OPTIONS'}],
        'access-control-allow-headers': [{'key': 'Access-Control-Allow-Headers', 'value': 'Content-Type, Authorization'}],
    }

    if headers:
        default_headers.update(headers)

    return {
        'status': str(status_code),
        'statusDescription': 'OK' if status_code == 200 else 'Error',
        'headers': default_headers,
        'body': json.dumps(body) if isinstance(body, (dict, list)) else body
    }

def handler(event, context):
    """
    Lambda@Edge handler for origin request events
    """
    try:
        request = event['Records'][0]['cf']['request']
        method = request['method']
        uri = unquote(request['uri'])
        query_string = request.get('querystring', '')

        # Parse query parameters
        query_params = parse_qs(query_string) if query_string else {}
        request_type = query_params.get('request', [None])[0]

        # Parse request body if present
        body = None
        if 'body' in request and request['body'].get('data'):
            try:
                body_data = request['body']['data']
                # Body might be base64 encoded
                if request['body'].get('encoding') == 'base64':
                    import base64
                    body_data = base64.b64decode(body_data).decode('utf-8')
                body = json.loads(body_data)
            except Exception as e:
                print(f"Error parsing body: {str(e)}")
                body = {}

        # Parse path
        collection, item_id = parse_path(uri)

        if not collection:
            return create_response(400, {
                'error': 'Invalid path',
                'message': 'Path must include at least a collection name'
            })

        print(f"Method: {method}, Collection: {collection}, Item ID: {item_id}, Request Type: {request_type}")

        # Handle CORS preflight
        if method == 'OPTIONS':
            return create_response(200, {})

        # Handle GET requests
        if method == 'GET':
            if item_id:
                # Get specific item
                item = get_item(collection, item_id)
                if item:
                    return create_response(200, item)
                else:
                    return create_response(404, {
                        'error': 'Not found',
                        'message': f'Item {item_id} not found in collection {collection}'
                    })
            else:
                # List all items in collection
                items = list_items_in_collection(collection)
                return create_response(200, {
                    'collection': collection,
                    'count': len(items),
                    'items': items
                })

        # Handle POST requests (create new item)
        elif method == 'POST':
            if not body:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Request body is required for POST'
                })

            # Check for bulk creation
            if request_type == 'bulk' and isinstance(body, list):
                created_items = []
                for item_data in body:
                    new_id = generate_id()
                    created_item = put_item(collection, new_id, item_data)
                    created_items.append(created_item)

                return create_response(201, {
                    'message': f'Created {len(created_items)} items',
                    'items': created_items
                })
            else:
                # Single item creation
                new_id = item_id if item_id else generate_id()
                created_item = put_item(collection, new_id, body)
                return create_response(201, created_item)

        # Handle PUT/PATCH requests (update item)
        elif method in ['PUT', 'PATCH']:
            if not item_id:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Item ID is required for PUT/PATCH'
                })

            if not body:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Request body is required for PUT/PATCH'
                })

            # For PATCH, merge with existing item
            if method == 'PATCH' or request_type != 'replace':
                existing_item = get_item(collection, item_id)
                if existing_item:
                    existing_item.update(body)
                    updated_item = put_item(collection, item_id, existing_item)
                else:
                    # If item doesn't exist, create it
                    updated_item = put_item(collection, item_id, body)
            else:
                # For PUT with replace, completely replace
                updated_item = put_item(collection, item_id, body)

            return create_response(200, updated_item)

        # Handle DELETE requests
        elif method == 'DELETE':
            if request_type == 'all':
                # Delete all items in collection
                delete_all_items(collection)
                return create_response(200, {
                    'message': f'All items deleted from collection {collection}'
                })
            elif item_id:
                # Delete specific item
                existing_item = get_item(collection, item_id)
                if not existing_item:
                    return create_response(404, {
                        'error': 'Not found',
                        'message': f'Item {item_id} not found in collection {collection}'
                    })

                delete_item(collection, item_id)
                return create_response(200, {
                    'message': f'Item {item_id} deleted from collection {collection}',
                    'deleted_item': existing_item
                })
            else:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Item ID is required for DELETE (or use ?request=all to delete all)'
                })

        else:
            return create_response(405, {
                'error': 'Method not allowed',
                'message': f'Method {method} is not supported'
            })

    except Exception as e:
        print(f"Error in handler: {str(e)}")
        import traceback
        traceback.print_exc()

        return create_response(500, {
            'error': 'Internal server error',
            'message': str(e)
        })
