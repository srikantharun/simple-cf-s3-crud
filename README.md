# CloudFront + S3 + Lambda@Edge CRUD API

A serverless CRUD (Create, Read, Update, Delete) API built with AWS CloudFront, S3, and Lambda@Edge. This solution enables full CRUD operations on an S3 backend through CloudFront, overcoming S3's native limitation of only supporting GET and HEAD methods.

## Architecture

```
┌─────────┐       ┌─────────────┐       ┌──────────────┐       ┌──────────┐
│ Client  │──────▶│  CloudFront │──────▶│ Lambda@Edge  │──────▶│ S3 Bucket│
│         │◀──────│             │◀──────│ (Origin Req) │◀──────│          │
└─────────┘       └─────────────┘       └──────────────┘       └──────────┘
                        │
                        ├─ Caching (GET)
                        ├─ HTTPS Enforcement
                        ├─ DDoS Protection
                        └─ Global Edge Locations
```

### Key Components

1. **S3 Bucket**: Stores data as JSON files with versioning enabled
2. **CloudFront Distribution**: Global CDN with edge caching
3. **Lambda@Edge (Origin Request)**: Intercepts all requests to handle CRUD operations
4. **Origin Access Control (OAC)**: Secures S3 bucket (CloudFront-only access)

### Why This Architecture?

**Problem**: S3 static website hosting only supports GET and HEAD methods. POST, PUT, PATCH, DELETE requests return `405 Method Not Allowed`.

**Solution**: Lambda@Edge functions run at CloudFront edge locations and can intercept requests before they reach S3. This allows us to:
- Handle POST/PUT/PATCH/DELETE operations programmatically
- Store data in S3 as structured JSON files
- Maintain RESTful API semantics
- Benefit from CloudFront's global CDN and caching

## Features

✅ **Full CRUD Operations**: GET, POST, PUT, PATCH, DELETE
✅ **Multi-path Support**: Nested collections (e.g., `/products/electronics/laptops`)
✅ **Query Parameters**: Filtering, bulk operations, and custom actions
✅ **S3 Persistent Storage**: All data stored as JSON files in S3
✅ **Versioning**: S3 versioning enabled for data recovery
✅ **Security**: Private S3 bucket with OAC, HTTPS enforcement
✅ **Caching**: GET requests cached at edge locations
✅ **Auto-scaling**: Serverless architecture scales automatically
✅ **CORS Support**: Cross-origin requests enabled
✅ **Encryption**: S3 server-side encryption (AES256)

## Prerequisites

- AWS Account with appropriate permissions
- Terraform >= 1.0
- AWS CLI configured with credentials
- `curl` for testing (optional)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/srikantharun/simple-cf-s3-crud.git
cd simple-cf-s3-crud
```

### 2. Configure Variables

Edit `variables.tf` or create `terraform.tfvars`:

```hcl
aws_region      = "us-east-1"
project_name    = "my-crud-api"
s3_bucket_name  = "my-unique-bucket-name-12345"  # Must be globally unique
environment     = "dev"
```

### 3. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Preview changes
terraform plan

# Deploy
terraform apply
```

**Note**: CloudFront distribution propagation takes 5-15 minutes after deployment.

### 4. Get API Endpoint

```bash
# Get CloudFront URL
terraform output cloudfront_url

# Example output: https://d1234567890.cloudfront.net
```

### 5. Test the API

```bash
# Run automated tests
./test_api.sh

# Or test manually
export API_URL=$(terraform output -raw cloudfront_url)

# Create an item
curl -X POST $API_URL/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Laptop","price":999.99}'

# List all items
curl $API_URL/items

# Get specific item
curl $API_URL/items/{item-id}

# Update item
curl -X PUT $API_URL/items/{item-id} \
  -H "Content-Type: application/json" \
  -d '{"price":899.99}'

# Delete item
curl -X DELETE $API_URL/items/{item-id}
```

## API Reference

### Supported Operations

#### GET - Read Operations

```bash
# List all items in a collection
GET /{collection}

# Get specific item by ID
GET /{collection}/{id}

# Filter items (future enhancement)
GET /{collection}?category=electronics
```

**Example**:
```bash
curl https://your-cloudfront-url.cloudfront.net/items
curl https://your-cloudfront-url.cloudfront.net/items/abc-123-def
```

#### POST - Create Operations

```bash
# Create a new item (auto-generates UUID)
POST /{collection}
Content-Type: application/json
Body: {"key":"value"}

# Bulk create multiple items
POST /{collection}?request=bulk
Content-Type: application/json
Body: [{"key":"value1"}, {"key":"value2"}]

# Create with specific ID
POST /{collection}/{id}
Content-Type: application/json
Body: {"key":"value"}
```

**Example**:
```bash
# Single item
curl -X POST https://your-cloudfront-url.cloudfront.net/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Laptop","category":"electronics","price":999.99}'

# Bulk create
curl -X POST https://your-cloudfront-url.cloudfront.net/items?request=bulk \
  -H "Content-Type: application/json" \
  -d '[{"name":"Mouse","price":29.99},{"name":"Keyboard","price":79.99}]'
```

#### PUT/PATCH - Update Operations

```bash
# Update item (merge with existing data)
PUT /{collection}/{id}
Content-Type: application/json
Body: {"key":"new_value"}

# Replace item completely
PUT /{collection}/{id}?request=replace
Content-Type: application/json
Body: {"key":"value"}

# Partial update (same as merge)
PATCH /{collection}/{id}
Content-Type: application/json
Body: {"key":"new_value"}
```

**Example**:
```bash
# Merge update
curl -X PUT https://your-cloudfront-url.cloudfront.net/items/abc-123 \
  -H "Content-Type: application/json" \
  -d '{"price":899.99,"stock":10}'

# Full replace
curl -X PUT https://your-cloudfront-url.cloudfront.net/items/abc-123?request=replace \
  -H "Content-Type: application/json" \
  -d '{"name":"Gaming Laptop","price":1299.99}'
```

#### DELETE - Delete Operations

```bash
# Delete specific item
DELETE /{collection}/{id}

# Delete all items in collection
DELETE /{collection}?request=all
```

**Example**:
```bash
# Delete specific item
curl -X DELETE https://your-cloudfront-url.cloudfront.net/items/abc-123

# Delete all items
curl -X DELETE https://your-cloudfront-url.cloudfront.net/items?request=all
```

#### OPTIONS - CORS Preflight

```bash
# CORS preflight request
OPTIONS /{collection}
```

### Response Format

#### Success Response

```json
{
  "id": "abc-123-def",
  "name": "Laptop",
  "category": "electronics",
  "price": 999.99,
  "created_at": "2024-12-03T10:30:00Z",
  "updated_at": "2024-12-03T10:30:00Z"
}
```

#### List Response

```json
{
  "collection": "items",
  "count": 2,
  "items": [
    {
      "id": "abc-123",
      "name": "Laptop",
      "price": 999.99
    },
    {
      "id": "def-456",
      "name": "Mouse",
      "price": 29.99
    }
  ]
}
```

#### Error Response

```json
{
  "error": "Not found",
  "message": "Item abc-123 not found in collection items"
}
```

### HTTP Status Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success (GET, PUT, PATCH, DELETE) |
| 201 | Created (POST) |
| 400 | Bad Request (invalid input) |
| 404 | Not Found (item doesn't exist) |
| 405 | Method Not Allowed |
| 500 | Internal Server Error |

## Collections and Paths

### Collection Naming

Collections can be simple or nested:

```bash
/items                          # Simple collection
/products                       # Simple collection
/products/electronics           # Nested collection
/products/electronics/laptops   # Deeply nested collection
/users/premium/members          # Multiple levels
/orders/2024/january            # Date-based nesting
```

### Data Storage in S3

Items are stored as individual JSON files in S3:

```
s3://your-bucket-name/
├── items/
│   ├── abc-123-def.json
│   ├── ghi-456-jkl.json
│   └── mno-789-pqr.json
├── products/
│   └── electronics/
│       ├── laptop-001.json
│       └── laptop-002.json
└── orders/
    └── 2024/
        └── january/
            └── order-12345.json
```

### Auto-generated Fields

Each item automatically includes:

- `id`: UUID (if not provided)
- `created_at`: ISO 8601 timestamp
- `updated_at`: ISO 8601 timestamp (updated on each modification)

## Configuration

### Terraform Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `aws_region` | string | us-east-1 | AWS region for resources |
| `project_name` | string | simple-cf-s3-crud | Project name prefix |
| `s3_bucket_name` | string | simple-cf-s3-crud-data-bucket | S3 bucket name (must be globally unique) |
| `environment` | string | dev | Environment (dev/staging/prod) |
| `cloudfront_price_class` | string | PriceClass_100 | CloudFront price tier |
| `lambda_timeout` | number | 30 | Lambda timeout (max 30 for origin request) |
| `lambda_memory_size` | number | 512 | Lambda memory in MB |
| `default_ttl` | number | 0 | Cache TTL (0 = no caching) |

### Customization

#### Change Cache TTL

To enable caching for GET requests (improves performance):

```hcl
# terraform.tfvars
default_ttl = 300  # 5 minutes
max_ttl     = 3600 # 1 hour
```

#### Custom Domain Name

To use a custom domain (e.g., `api.example.com`):

1. Create ACM certificate in us-east-1
2. Add to CloudFront distribution:

```hcl
# In main.tf, update aws_cloudfront_distribution
aliases = ["api.example.com"]

viewer_certificate {
  acm_certificate_arn      = "arn:aws:acm:us-east-1:..."
  ssl_support_method       = "sni-only"
  minimum_protocol_version = "TLSv1.2_2021"
}
```

3. Create Route53 CNAME record pointing to CloudFront domain

## Security Considerations

### Current Security Features

✅ **Private S3 Bucket**: No public access, only CloudFront can read
✅ **Origin Access Control (OAC)**: Modern replacement for Origin Access Identity
✅ **HTTPS Enforcement**: All HTTP requests redirected to HTTPS
✅ **Encryption at Rest**: S3 server-side encryption (AES256)
✅ **Encryption in Transit**: TLS 1.2+ enforced
✅ **Versioning**: S3 versioning enabled for data recovery
✅ **IAM Least Privilege**: Lambda@Edge has minimal S3 permissions

### Production Hardening Recommendations

For production deployments, implement these additional security measures:

#### 1. Authentication & Authorization

```hcl
# Add Lambda@Edge authorizer for viewer request
resource "aws_lambda_function" "authorizer" {
  # Validate JWT tokens, API keys, or custom auth
}
```

#### 2. Rate Limiting

```hcl
# Use AWS WAF with rate-based rules
resource "aws_wafv2_web_acl" "rate_limit" {
  # Rate limit rules
}
```

#### 3. Input Validation

```python
# In lambda_edge_crud.py, add input validation
import jsonschema

schema = {
  "type": "object",
  "properties": {
    "name": {"type": "string", "maxLength": 100},
    "price": {"type": "number", "minimum": 0}
  },
  "required": ["name"]
}

jsonschema.validate(body, schema)
```

#### 4. WAF Rules

```hcl
resource "aws_wafv2_web_acl" "cloudfront_waf" {
  # AWS Managed Rule Sets
  # SQL injection protection
  # XSS protection
  # Rate limiting
}
```

#### 5. CloudWatch Alarms

```hcl
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  # Alert on Lambda errors
  # Alert on high latency
  # Alert on unusual traffic patterns
}
```

#### 6. VPC for Lambda@Edge (Limited Support)

Note: Lambda@Edge has limited VPC support. For private resources, consider using VPC Endpoints or PrivateLink.

## Monitoring and Debugging

### CloudWatch Logs

Lambda@Edge logs are created in CloudWatch Logs in the region where the function executes (edge locations worldwide).

```bash
# View logs in us-east-1 (and other edge regions)
aws logs tail /aws/lambda/us-east-1.simple-cf-s3-crud-edge-crud --follow
```

### CloudFront Metrics

Monitor in CloudFront console:
- Requests count
- Error rate (4xx, 5xx)
- Cache hit ratio
- Data transfer

### S3 Bucket Monitoring

```bash
# List all items in bucket
aws s3 ls s3://your-bucket-name/ --recursive

# View specific item
aws s3 cp s3://your-bucket-name/items/abc-123.json -

# Check bucket size
aws s3 ls s3://your-bucket-name --recursive --summarize --human-readable
```

### Debug Tips

1. **CloudFront Propagation Delays**: Wait 5-15 minutes after deployment
2. **Lambda@Edge Cold Starts**: First request may be slow
3. **Caching Issues**: Add `Cache-Control: no-cache` header for testing
4. **CORS Errors**: Check browser console for preflight requests
5. **500 Errors**: Check Lambda CloudWatch logs in edge region

## Cost Estimation

### Monthly Cost Breakdown (Approximate)

Based on 1 million requests/month:

| Service | Usage | Cost |
|---------|-------|------|
| CloudFront | 1M requests, 10GB transfer | $0.85 + $0.85 = $1.70 |
| Lambda@Edge | 1M requests, 128MB, 100ms avg | $0.60 + $0.50 = $1.10 |
| S3 Storage | 1GB stored, 1M PUT/GET | $0.023 + $0.50 = $0.52 |
| CloudWatch Logs | 1GB logs | $0.50 |
| **Total** | | **~$3.82/month** |

### Cost Optimization Tips

1. **Enable CloudFront Caching**: Reduce Lambda@Edge invocations
2. **Use S3 Lifecycle Policies**: Archive old data to Glacier
3. **Optimize Lambda Memory**: Lower memory = lower cost
4. **Use CloudFront PriceClass_100**: Only US/Europe edge locations

## Comparison: Lambda+API Gateway vs Lambda@Edge+S3

| Feature | Lambda + API Gateway | Lambda@Edge + S3 |
|---------|---------------------|------------------|
| **Storage** | External (DynamoDB/RDS) | S3 (built-in) |
| **Latency** | Regional (single region) | Global edge locations |
| **Cold Starts** | Higher | Lower (edge caching) |
| **Cost** | Higher (API Gateway fees) | Lower (no API Gateway) |
| **Scalability** | Auto-scales (regional) | Auto-scales (global) |
| **Complexity** | Lower | Higher |
| **Use Case** | Backend APIs | Static-like CRUD with S3 |

## Troubleshooting

### Issue: 405 Method Not Allowed

**Cause**: Request is reaching S3 directly instead of Lambda@Edge
**Solution**: Ensure Lambda@Edge is properly associated with CloudFront distribution

```bash
terraform apply  # Reapply configuration
```

### Issue: 403 Forbidden

**Cause**: S3 bucket policy or OAC misconfiguration
**Solution**: Check S3 bucket policy allows CloudFront

```bash
aws s3api get-bucket-policy --bucket your-bucket-name
```

### Issue: 500 Internal Server Error

**Cause**: Lambda@Edge function error
**Solution**: Check CloudWatch Logs

```bash
aws logs tail /aws/lambda/us-east-1.simple-cf-s3-crud-edge-crud --follow --filter-pattern ERROR
```

### Issue: CloudFront URL Returns "Not Found"

**Cause**: CloudFront distribution still propagating
**Solution**: Wait 5-15 minutes after `terraform apply`

```bash
# Check distribution status
aws cloudfront get-distribution --id YOUR_DISTRIBUTION_ID | grep Status
```

## Cleanup

To avoid ongoing AWS charges, destroy all resources:

```bash
# Delete all items in S3 (required before destroying bucket)
aws s3 rm s3://your-bucket-name --recursive

# Destroy infrastructure
terraform destroy

# Confirm by typing 'yes' when prompted
```

**Note**: CloudFront distribution deletion may take 15-30 minutes.

## Roadmap

Future enhancements:

- [ ] DynamoDB integration for faster queries
- [ ] ElasticSearch for full-text search
- [ ] Pagination support (limit/offset)
- [ ] Field-based filtering (?category=electronics)
- [ ] Sorting (?sort=price&order=asc)
- [ ] Authentication (JWT, API Keys)
- [ ] Rate limiting per user
- [ ] Batch operations optimization
- [ ] GraphQL API support
- [ ] WebSocket support for real-time updates

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is open source and available under the MIT License.

## Resources

- [AWS Lambda@Edge Documentation](https://docs.aws.amazon.com/lambda/latest/dg/lambda-edge.html)
- [CloudFront Developer Guide](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/)
- [S3 Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/best-practices.html)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

## Support

For issues and questions:

- GitHub Issues: https://github.com/srikantharun/simple-cf-s3-crud/issues
- AWS Support: https://aws.amazon.com/support/

---

**Built with ❤️ using AWS Lambda@Edge, CloudFront, and S3**
