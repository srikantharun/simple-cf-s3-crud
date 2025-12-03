variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "simple-cf-s3-crud"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for storing CRUD data (must be globally unique)"
  type        = string
  default     = "simple-cf-s3-crud-data-bucket"
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (PriceClass_100, PriceClass_200, PriceClass_All)"
  type        = string
  default     = "PriceClass_100"
}

variable "enable_cloudfront_logging" {
  description = "Enable CloudFront access logging"
  type        = bool
  default     = false
}

variable "lambda_timeout" {
  description = "Lambda@Edge function timeout in seconds (max 30 for origin request)"
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Lambda@Edge function memory size in MB"
  type        = number
  default     = 512
}

variable "allowed_methods" {
  description = "HTTP methods allowed by CloudFront"
  type        = list(string)
  default     = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
}

variable "cached_methods" {
  description = "HTTP methods to cache"
  type        = list(string)
  default     = ["GET", "HEAD", "OPTIONS"]
}

variable "default_ttl" {
  description = "Default TTL for cached objects (seconds)"
  type        = number
  default     = 0
}

variable "max_ttl" {
  description = "Maximum TTL for cached objects (seconds)"
  type        = number
  default     = 0
}

variable "min_ttl" {
  description = "Minimum TTL for cached objects (seconds)"
  type        = number
  default     = 0
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "simple-cf-s3-crud"
    Environment = "dev"
    ManagedBy   = "terraform"
    Owner       = "devops-team"
  }
}
