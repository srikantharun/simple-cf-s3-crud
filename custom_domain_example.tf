# OPTIONAL: Custom Domain Configuration
# Uncomment and configure if you want to use a custom domain like api.yourcompany.com

# Note: This is just an example file. To use it:
# 1. Copy contents to main.tf
# 2. Create ACM certificate in us-east-1 via AWS Console
# 3. Update the certificate ARN below
# 4. Add DNS record in Route53 or your DNS provider

/*
variable "custom_domain_name" {
  description = "Custom domain name for the API (e.g., api.yourcompany.com)"
  type        = string
  default     = "api.yourcompany.com"
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for custom domain (must be in us-east-1)"
  type        = string
  default     = "arn:aws:acm:us-east-1:123456789012:certificate/abcd-1234-..."
}

# Update the CloudFront distribution in main.tf:

resource "aws_cloudfront_distribution" "s3_distribution" {
  # ... existing configuration ...

  # Add this:
  aliases = [var.custom_domain_name]

  # Replace viewer_certificate block with:
  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# Add Route53 record (if using Route53):
data "aws_route53_zone" "main" {
  name         = "yourcompany.com"
  private_zone = false
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.custom_domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.s3_distribution.domain_name
    zone_id                = aws_cloudfront_distribution.s3_distribution.hosted_zone_id
    evaluate_target_health = false
  }
}
*/
