# WAF Policy Generator (Donutnt-Gen)

Converts YAML configuration files to Terraform files and generates test cases with curl commands for AWS WAF.

## Features

- **YAML-based Configuration**: Define WAF policies in human-readable YAML
- **ABCD ABC-XYZ Patterns**: Supports detection-exception-catchall flow
- **Label-based Rules**: Full support for label matching and exception patterns
- **Test Generation**: Auto-generates curl-based test scripts
- **Multiple Rule Types**: IP sets, AWS managed rules, custom rules

## Installation

```bash
cd donutnt-gen
pip install -r requirements.txt
```

## Quick Start

```bash
# Generate Terraform + Tests
python generator/waf_generator.py --config configs/example_policy.yaml --output ./output

# Validate only
python generator/waf_generator.py --config configs/example_policy.yaml --validate-only

# Generate tests only
python generator/waf_generator.py --config configs/example_policy.yaml --tests-only

# Debug mode
python generator/waf_generator.py --config configs/example_policy.yaml --debug
```

## Architecture Pattern

The WAF policy follows a detection-then-exception-then-block flow:

```
Request
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 1: size-restrictions (Detection, COUNT)            │
│   → Adds label: abcd:cyber:custom:owasp:restrict-sizes   │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 2: log4j-150 (AWS Managed, BLOCK)                  │
│   → AWSManagedRulesKnownBadInputsRuleSet                 │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 3: ip-blacklist (BLOCK)                            │
│   → Blocks known bad IPs                                 │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 4: owasp-detection (Detection, COUNT)              │
│   → Adds labels: mitigate-sqli, mitigate-xss             │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 5: exception-rules (Exception, COUNT)              │
│   → Checks: threat-label + method + host + uri           │
│   → Adds labels: abcd-found-sql-false-positive, etc.     │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Order 6-8: catch-all rules (BLOCK)                       │
│   → BLOCKS if: threat-label AND NOT exception-label      │
└──────────────────────────────────────────────────────────┘
   │
   ▼
 ALLOW (Default Action)
```

## YAML Configuration

### Metadata

```yaml
version: "1.0"
metadata:
  project: "donutv8"
  policy_name: "custom_donut_global_block_version_8"
  account_id: "052407073588"
  environment: "production"
  owner: "ABC-XYZ"
```

### Settings

```yaml
settings:
  scope: "CLOUDFRONT"        # CLOUDFRONT or REGIONAL
  default_action: "allow"    # allow, block, or count
  cloudwatch_metrics_enabled: true
  sampled_requests_enabled: true
```

### Allowed Hosts (Reusable)

```yaml
allowed_hosts:
  - host: "api.example.com"
    match: "EXACTLY"
  - host: ".example.com"
    match: "ENDS_WITH"
```

### Rule Groups

#### Custom Rule Group

```yaml
rule_groups:
  owasp_detection:
    order: 4
    type: "custom"
    name: "custom-owasp-top10"
    capacity: 900
    namespace: "abcd:cyber:custom:owasp"
    rules:
      - name: "detect-sqli-body"
        priority: 1
        action: "count"
        label: "mitigate-sqli"
        statement:
          sqli_match:
            field: "BODY"
            text_transformations:
              - priority: 0
                type: "URL_DECODE"
```

#### Exception Rule Pattern

```yaml
  exception_rules:
    order: 5
    type: "custom"
    name: "donutv8-custom"
    namespace: "custom"
    rules:
      - name: "custom-10007"
        priority: 1
        action: "count"
        label: "abcd-found-sql-false-positive"
        statement:
          and:
            - label_match:
                scope: "LABEL"
                key: "awswaf:${account_id}:rulegroup:custom-owasp-top10:abcd:cyber:custom:owasp:mitigate-sqli"
            - or_methods: ["post"]
            - or_hosts: "${allowed_hosts}"
            - byte_match:
                field: "URI_PATH"
                search_string: "/api/upload"
                positional_constraint: "STARTS_WITH"
```

#### Catch-All Block Pattern

```yaml
  sql_catch_all:
    order: 7
    type: "custom"
    name: "custom-sql-catch-all"
    rules:
      - name: "block-sqli"
        priority: 0
        action: "block"
        custom_response:
          response_code: 403
          custom_response_body_key: "abcd-default-block"
        statement:
          and:
            - label_match:
                scope: "LABEL"
                key: "awswaf:${account_id}:rulegroup:custom-owasp-top10:abcd:cyber:custom:owasp:mitigate-sqli"
            - not:
                label_match:
                  scope: "LABEL"
                  key: "awswaf:${account_id}:rulegroup:donutv8-custom:custom:abcd-found-sql-false-positive"
```

## Special Statement Shorthands

### or_methods

Expands to OR statement matching HTTP methods:

```yaml
- or_methods: ["post", "put"]
```

### or_hosts

References `allowed_hosts` for OR statement:

```yaml
- or_hosts: "${allowed_hosts}"
```

## Test Definitions

```yaml
test_definitions:
  settings:
    base_url: "https://example.com"
    test_data_dir: "./test_data"

  test_suites:
    - name: "sql_injection_tests"
      description: "SQLi payloads should be blocked"
      tests:
        - id: "sqli-001"
          name: "SQLi in query string"
          type: "true_positive"
          expected_status: 403
          request:
            method: "POST"
            uri: "/api/endpoint"
            query_string: "id=1+union+select+1"
            headers:
              Content-Type: "application/json"
```

## Output Structure

```
output/{project}/
├── terraform/
│   ├── main.tf
│   ├── versions.tf
│   ├── variables.tf
│   ├── waf_acl.tf
│   ├── waf_rule_groups.tf
│   ├── waf_ip_sets.tf
│   └── outputs.tf
└── tests/
    ├── test_cases.yaml
    ├── test_runner.sh
    └── test_report.md
```

## Running Tests

```bash
# Run all tests
cd output/donutv8/tests
./test_runner.sh

# Custom base URL
BASE_URL=https://your-domain.com ./test_runner.sh

# Verbose mode
VERBOSE=1 ./test_runner.sh
```

## Test Types

| Type | Description | Expected |
|------|-------------|----------|
| `true_positive` | Malicious requests | 403 (blocked) |
| `false_positive` | Legitimate requests | 200 (allowed) |
| `boundary` | Edge case tests | Varies |
| `gamified` | Attacks with valid params | 403 (blocked) |

## Label Naming Convention

```
Threat Labels:
awswaf:{account_id}:rulegroup:{rule_group_name}:{namespace}:{label_name}

Exception Labels:
awswaf:{account_id}:rulegroup:{rule_group_name}:custom:{label_name}
```

## License

MIT License
