# Origin Access Control (modern replacement for OAI)
resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "${var.project_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
  description                       = "OAC for ${var.bucket_name}"
}

# Security headers policy
resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${var.project_name}-security-headers"

  security_headers_config {
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "SAMEORIGIN"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    xss_protection {
      protection = true
      mode_block = true
      override   = true
    }
  }
}

# Cache policy for static assets (used for static content paths if needed)
resource "aws_cloudfront_cache_policy" "static" {
  name = "${var.project_name}-static-cache"

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }

  default_ttl = 86400
  max_ttl     = 31536000
  min_ttl     = 0
}

# Cache policy for API/CRUD operations (no caching)
resource "aws_cloudfront_cache_policy" "api" {
  name = "${var.project_name}-api-cache"

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = ["Authorization", "Content-Type", "Accept"]
      }
    }
    query_strings_config {
      query_string_behavior = "all"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }

  default_ttl = 0
  max_ttl     = 0
  min_ttl     = 0
}

# Origin request policy for API (forwards body for POST/PUT)
resource "aws_cloudfront_origin_request_policy" "api" {
  name = "${var.project_name}-api-origin-request"

  cookies_config {
    cookie_behavior = "none"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["Authorization", "Content-Type", "Accept", "Origin"]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

# Distribution using S3 REST endpoint + OAC (bucket remains private)
resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} - S3 CRUD API with Lambda@Edge"
  default_root_object = var.enable_crud_api ? "" : var.website_index
  price_class         = var.price_class

  origin {
    domain_name              = "${aws_s3_bucket.site_bucket.bucket}.s3.${var.aws_region}.amazonaws.com"
    origin_id                = "s3-site-origin"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-site-origin"
    viewer_protocol_policy = "redirect-to-https"

    # CRUD operations require all HTTP methods
    allowed_methods = var.enable_crud_api ? ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"] : ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]

    # Use API cache policy (no caching) when CRUD is enabled
    cache_policy_id            = var.enable_crud_api ? aws_cloudfront_cache_policy.api.id : aws_cloudfront_cache_policy.static.id
    origin_request_policy_id   = var.enable_crud_api ? aws_cloudfront_origin_request_policy.api.id : null
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

    compress = true

    # Lambda@Edge association for CRUD operations
    dynamic "lambda_function_association" {
      for_each = var.enable_crud_api ? [1] : []
      content {
        event_type   = "origin-request"
        lambda_arn   = aws_lambda_function.edge_crud.qualified_arn
        include_body = true
      }
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

  tags = var.tags

  depends_on = [aws_lambda_function.edge_crud]
}

# Outputs
output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.site.id
}

output "cloudfront_url" {
  description = "Full CloudFront HTTPS URL"
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "api_examples" {
  description = "Example CRUD API commands"
  value = var.enable_crud_api ? {
    list_items   = "curl https://${aws_cloudfront_distribution.site.domain_name}/items"
    create_item  = "curl -X POST https://${aws_cloudfront_distribution.site.domain_name}/items -H 'Content-Type: application/json' -d '{\"name\":\"Test\"}'"
    get_item     = "curl https://${aws_cloudfront_distribution.site.domain_name}/items/{id}"
    update_item  = "curl -X PUT https://${aws_cloudfront_distribution.site.domain_name}/items/{id} -H 'Content-Type: application/json' -d '{\"name\":\"Updated\"}'"
    delete_item  = "curl -X DELETE https://${aws_cloudfront_distribution.site.domain_name}/items/{id}"
  } : null
}
