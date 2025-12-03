#############################################
# Lambda@Edge Function for CRUD Operations
# NOTE: Lambda@Edge MUST be deployed in us-east-1
#############################################

# Package Lambda function
data "archive_file" "lambda_edge_crud" {
  type        = "zip"
  source_file = "${path.module}/lambda_edge_crud.py"
  output_path = "${path.module}/lambda_edge_crud.zip"
}

# IAM Role for Lambda@Edge
resource "aws_iam_role" "lambda_edge" {
  name = "${var.project_name}-lambda-edge-role"

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

  tags = var.tags
}

# IAM Policy - CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_edge_basic" {
  role       = aws_iam_role.lambda_edge.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# IAM Policy - S3 Access for CRUD operations
resource "aws_iam_role_policy" "lambda_edge_s3" {
  name = "${var.project_name}-lambda-edge-s3-policy"
  role = aws_iam_role.lambda_edge.id

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
          aws_s3_bucket.site_bucket.arn,
          "${aws_s3_bucket.site_bucket.arn}/*"
        ]
      }
    ]
  })
}

# Lambda@Edge Function
# IMPORTANT: No environment block - Lambda@Edge does not support env vars
resource "aws_lambda_function" "edge_crud" {
  filename         = data.archive_file.lambda_edge_crud.output_path
  function_name    = "${var.project_name}-edge-crud"
  role             = aws_iam_role.lambda_edge.arn
  handler          = "lambda_edge_crud.handler"
  source_code_hash = data.archive_file.lambda_edge_crud.output_base64sha256
  runtime          = "python3.12"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  publish          = true  # Required for Lambda@Edge

  # NOTE: Lambda@Edge does NOT support environment variables
  # Bucket name is extracted from CloudFront origin in the Lambda code

  tags = var.tags
}

# Output the Lambda ARN for reference
output "lambda_edge_arn" {
  description = "Lambda@Edge function qualified ARN"
  value       = aws_lambda_function.edge_crud.qualified_arn
}
