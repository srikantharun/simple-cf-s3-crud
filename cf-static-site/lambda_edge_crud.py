"""
Lambda@Edge function for handling CRUD operations with S3 backend
This function runs on Origin Request events in CloudFront

IMPORTANT: Lambda@Edge does NOT support environment variables.
The bucket name is extracted from the CloudFront origin configuration.
"""

import json
import boto3
import uuid
from datetime import datetime
from urllib.parse import parse_qs, unquote

s3_client = boto3.client('s3')


def get_bucket_from_request(request):
    """
    Extract bucket name from CloudFront origin domain.
    The domain looks like: "bucket-name.s3.us-east-1.amazonaws.com"
    or "bucket-name.s3.amazonaws.com"
    """
    origin = request.get('origin', {})
    s3_origin = origin.get('s3', {})
    domain = s3_origin.get('domainName', '')

    if domain:
        # Extract bucket name from domain (first part before .s3.)
        bucket_name = domain.split('.s3.')[0]
        return bucket_name

    # Fallback - should not reach here if CloudFront is configured correctly
    return None


def generate_id():
    """Generate a unique ID for new items"""
    return str(uuid.uuid4())


def parse_path(path):
    """
    Parse the request path to extract collection and item ID
    Examples:
      /items -> collection='items', item_id=None
      /items/123 -> collection='items', item_id='123'
      /products/electronics -> collection='products/electronics', item_id=None
    """
    path = path.strip('/')
    if not path:
        return None, None

    parts = path.split('/')

    if len(parts) > 1:
        last_part = parts[-1]
        # Check if last part looks like a UUID or ID
        if '-' in last_part or len(last_part) == 36:
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
    return f"{collection}/"


def list_items_in_collection(bucket_name, collection):
    """List all items in a collection"""
    try:
        prefix = f"{collection}/"
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )

        items = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.json'):
                    try:
                        obj_response = s3_client.get_object(
                            Bucket=bucket_name,
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


def get_item(bucket_name, collection, item_id):
    """Get a specific item from S3"""
    try:
        key = get_s3_key(collection, item_id)
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"Error getting item: {str(e)}")
        raise


def put_item(bucket_name, collection, item_id, data):
    """Store an item in S3"""
    try:
        key = get_s3_key(collection, item_id)

        if 'id' not in data:
            data['id'] = item_id
        if 'created_at' not in data:
            data['created_at'] = datetime.utcnow().isoformat() + 'Z'
        data['updated_at'] = datetime.utcnow().isoformat() + 'Z'

        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        return data
    except Exception as e:
        print(f"Error putting item: {str(e)}")
        raise


def delete_item(bucket_name, collection, item_id):
    """Delete a specific item from S3"""
    try:
        key = get_s3_key(collection, item_id)
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        return True
    except Exception as e:
        print(f"Error deleting item: {str(e)}")
        raise


def delete_all_items(bucket_name, collection):
    """Delete all items in a collection"""
    try:
        prefix = f"{collection}/"
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        if 'Contents' in response:
            for obj in response['Contents']:
                s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
        return True
    except Exception as e:
        print(f"Error deleting all items: {str(e)}")
        raise


def create_response(status_code, body, headers=None):
    """Create a CloudFront response"""
    status_map = {
        200: 'OK',
        201: 'Created',
        400: 'Bad Request',
        404: 'Not Found',
        405: 'Method Not Allowed',
        500: 'Internal Server Error'
    }

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
        'statusDescription': status_map.get(status_code, 'Error'),
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

        # Get bucket name from CloudFront origin
        bucket_name = get_bucket_from_request(request)
        if not bucket_name:
            return create_response(500, {'error': 'Could not determine bucket name'})

        # Parse query parameters
        query_params = parse_qs(query_string) if query_string else {}
        request_type = query_params.get('request', [None])[0]

        # Parse request body if present
        body = None
        if 'body' in request and request['body'].get('data'):
            try:
                body_data = request['body']['data']
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

        print(f"Method: {method}, Collection: {collection}, Item ID: {item_id}, Bucket: {bucket_name}")

        # Handle CORS preflight
        if method == 'OPTIONS':
            return create_response(200, {})

        # Handle GET requests
        if method == 'GET':
            if item_id:
                item = get_item(bucket_name, collection, item_id)
                if item:
                    return create_response(200, item)
                return create_response(404, {
                    'error': 'Not found',
                    'message': f'Item {item_id} not found in collection {collection}'
                })
            else:
                items = list_items_in_collection(bucket_name, collection)
                return create_response(200, {
                    'collection': collection,
                    'count': len(items),
                    'items': items
                })

        # Handle POST requests (create)
        elif method == 'POST':
            if not body:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Request body is required for POST'
                })

            if request_type == 'bulk' and isinstance(body, list):
                created_items = []
                for item_data in body:
                    new_id = generate_id()
                    created_item = put_item(bucket_name, collection, new_id, item_data)
                    created_items.append(created_item)
                return create_response(201, {
                    'message': f'Created {len(created_items)} items',
                    'items': created_items
                })
            else:
                new_id = item_id if item_id else generate_id()
                created_item = put_item(bucket_name, collection, new_id, body)
                return create_response(201, created_item)

        # Handle PUT/PATCH requests (update)
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

            if method == 'PATCH' or request_type != 'replace':
                existing_item = get_item(bucket_name, collection, item_id)
                if existing_item:
                    existing_item.update(body)
                    updated_item = put_item(bucket_name, collection, item_id, existing_item)
                else:
                    updated_item = put_item(bucket_name, collection, item_id, body)
            else:
                updated_item = put_item(bucket_name, collection, item_id, body)

            return create_response(200, updated_item)

        # Handle DELETE requests
        elif method == 'DELETE':
            if request_type == 'all':
                delete_all_items(bucket_name, collection)
                return create_response(200, {
                    'message': f'All items deleted from collection {collection}'
                })
            elif item_id:
                existing_item = get_item(bucket_name, collection, item_id)
                if not existing_item:
                    return create_response(404, {
                        'error': 'Not found',
                        'message': f'Item {item_id} not found in collection {collection}'
                    })
                delete_item(bucket_name, collection, item_id)
                return create_response(200, {
                    'message': f'Item {item_id} deleted',
                    'deleted_item': existing_item
                })
            else:
                return create_response(400, {
                    'error': 'Bad request',
                    'message': 'Item ID required for DELETE (or use ?request=all)'
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
