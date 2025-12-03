variable "aws_region" {
  description = "Region for S3 and auxiliary resources (ACM for CF must be us-east-1)"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name/tag prefix"
  type        = string
}

variable "bucket_name" {
  description = "S3 bucket name for the site"
  type        = string
}

variable "website_index" {
  description = "Default root object served by CloudFront"
  type        = string
  default     = "index.html"
}

variable "logging_enabled" {
  description = "Enable CloudFront access logging to S3"
  type        = bool
  default     = false
}

variable "logging_bucket" {
  description = "S3 bucket name for CloudFront logs. Required if logging_enabled=true"
  type        = string
  default     = ""
}

variable "price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags (e.g. map(BusinessUnit,XYZ))"
  default = {
    terraform          = "true"
    gitrepo            = "https://xxxxxxxxxxxx/WAF-COE/terraform-aws-cloudfront"
    owner              = "GSC Core Team"
    Purpose            = "Firewall Manager security policies"
    dataclassification = "internal"
  }
}

#############################################
# Lambda@Edge / CRUD API Variables
#############################################

variable "enable_crud_api" {
  description = "Enable CRUD API via Lambda@Edge (POST, PUT, DELETE support)"
  type        = bool
  default     = true
}

variable "lambda_timeout" {
  description = "Lambda@Edge function timeout in seconds (max 30 for origin-request)"
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Lambda@Edge function memory size in MB"
  type        = number
  default     = 512
}
