terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

# Primary provider (can be any region for most resources)
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.common_tags
  }
}

# Lambda@Edge functions MUST be created in us-east-1
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = var.common_tags
  }
}

#############################################
# S3 Bucket for Data Storage
#############################################

resource "aws_s3_bucket" "data_bucket" {
  bucket = var.s3_bucket_name

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-data-bucket"
    }
  )
}

resource "aws_s3_bucket_versioning" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#############################################
# CloudFront Origin Access Control (OAC)
#############################################

resource "aws_cloudfront_origin_access_control" "s3_oac" {
  name                              = "${var.project_name}-s3-oac"
  description                       = "OAC for S3 bucket access"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

#############################################
# S3 Bucket Policy - Allow CloudFront OAC
#############################################

data "aws_iam_policy_document" "s3_bucket_policy" {
  statement {
    sid    = "AllowCloudFrontServicePrincipal"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.data_bucket.arn,
      "${aws_s3_bucket.data_bucket.arn}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.s3_distribution.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id
  policy = data.aws_iam_policy_document.s3_bucket_policy.json

  depends_on = [aws_cloudfront_distribution.s3_distribution]
}

#############################################
# Lambda@Edge Function for CRUD Operations
#############################################

# Package Lambda function
data "archive_file" "lambda_edge_package" {
  type        = "zip"
  source_file = "${path.module}/lambda_edge_crud.py"
  output_path = "${path.module}/lambda_edge_crud.zip"
}

# IAM Role for Lambda@Edge
resource "aws_iam_role" "lambda_edge_role" {
  provider = aws.us_east_1
  name     = "${var.project_name}-lambda-edge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = [
            "lambda.amazonaws.com",
            "edgelambda.amazonaws.com"
          ]
        }
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-lambda-edge-role"
    }
  )
}

# IAM Policy for Lambda@Edge - CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_edge_basic" {
  provider   = aws.us_east_1
  role       = aws_iam_role.lambda_edge_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# IAM Policy for Lambda@Edge - S3 Access
resource "aws_iam_role_policy" "lambda_edge_s3_policy" {
  provider = aws.us_east_1
  name     = "${var.project_name}-lambda-edge-s3-policy"
  role     = aws_iam_role.lambda_edge_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.data_bucket.arn,
          "${aws_s3_bucket.data_bucket.arn}/*"
        ]
      }
    ]
  })
}

# Lambda@Edge Function (must be in us-east-1)
resource "aws_lambda_function" "edge_crud_function" {
  provider         = aws.us_east_1
  filename         = data.archive_file.lambda_edge_package.output_path
  function_name    = "${var.project_name}-edge-crud"
  role             = aws_iam_role.lambda_edge_role.arn
  handler          = "lambda_edge_crud.handler"
  source_code_hash = data.archive_file.lambda_edge_package.output_base64sha256
  runtime          = "python3.12"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  publish          = true # Required for Lambda@Edge

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.data_bucket.id
    }
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-edge-crud-function"
    }
  )
}

#############################################
# CloudFront Distribution
#############################################

resource "aws_cloudfront_distribution" "s3_distribution" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} - S3 CRUD API with Lambda@Edge"
  default_root_object = ""
  price_class         = var.cloudfront_price_class

  origin {
    domain_name              = aws_s3_bucket.data_bucket.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.data_bucket.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3_oac.id
  }

  default_cache_behavior {
    allowed_methods  = var.allowed_methods
    cached_methods   = var.cached_methods
    target_origin_id = "S3-${aws_s3_bucket.data_bucket.id}"

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Accept"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = var.min_ttl
    default_ttl            = var.default_ttl
    max_ttl                = var.max_ttl
    compress               = true

    # Lambda@Edge association for origin request
    lambda_function_association {
      event_type   = "origin-request"
      lambda_arn   = aws_lambda_function.edge_crud_function.qualified_arn
      include_body = true
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-cloudfront"
    }
  )
}

#############################################
# Outputs
#############################################

output "s3_bucket_name" {
  description = "Name of the S3 bucket storing data"
  value       = aws_s3_bucket.data_bucket.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.data_bucket.arn
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.s3_distribution.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.s3_distribution.id
}

output "cloudfront_url" {
  description = "Full CloudFront HTTPS URL"
  value       = "https://${aws_cloudfront_distribution.s3_distribution.domain_name}"
}

output "lambda_edge_function_name" {
  description = "Lambda@Edge function name"
  value       = aws_lambda_function.edge_crud_function.function_name
}

output "lambda_edge_function_arn" {
  description = "Lambda@Edge function ARN"
  value       = aws_lambda_function.edge_crud_function.qualified_arn
}

output "api_endpoint_examples" {
  description = "Example API endpoints"
  value = {
    list_items     = "https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items"
    get_item       = "https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items/{id}"
    create_item    = "curl -X POST https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items -H 'Content-Type: application/json' -d '{\"name\":\"Test Item\"}'"
    update_item    = "curl -X PUT https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items/{id} -H 'Content-Type: application/json' -d '{\"name\":\"Updated\"}'"
    delete_item    = "curl -X DELETE https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items/{id}"
    delete_all     = "curl -X DELETE https://${aws_cloudfront_distribution.s3_distribution.domain_name}/items?request=all"
  }
}

output "deployment_notes" {
  description = "Important notes about this deployment"
  value = <<-EOT
    ============================================================
    SIMPLE CLOUDFRONT + S3 + LAMBDA@EDGE CRUD API
    ============================================================

    Architecture:
      Client → CloudFront → Lambda@Edge → S3 Bucket

    Components:
      - S3 Bucket: ${aws_s3_bucket.data_bucket.id}
      - CloudFront: ${aws_cloudfront_distribution.s3_distribution.domain_name}
      - Lambda@Edge: ${aws_lambda_function.edge_crud_function.function_name}

    Supported Operations:
      GET    /{collection}         - List all items
      GET    /{collection}/{id}    - Get specific item
      POST   /{collection}         - Create new item
      POST   /{collection}?request=bulk - Bulk create
      PUT    /{collection}/{id}    - Update item (merge)
      PUT    /{collection}/{id}?request=replace - Replace item
      PATCH  /{collection}/{id}    - Partial update
      DELETE /{collection}/{id}    - Delete item
      DELETE /{collection}?request=all - Delete all items

    Example Collections:
      /items
      /products/electronics
      /users/premium
      /orders/2024

    Data Storage:
      Items are stored in S3 as JSON files:
      s3://${aws_s3_bucket.data_bucket.id}/{collection}/{id}.json

    Security:
      - S3 bucket is private (no public access)
      - Access only via CloudFront with OAC
      - HTTPS enforced
      - Versioning enabled

    Notes:
      - Lambda@Edge runs in us-east-1 (required)
      - CloudFront propagation takes 5-15 minutes
      - GET requests are cached (TTL: ${var.default_ttl}s)
      - POST/PUT/DELETE bypass cache

    ============================================================
  EOT
}
