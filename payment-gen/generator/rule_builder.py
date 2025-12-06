"""
Rule building functions for WAF Terraform generation.
Handles the ABCD ABC-XYZ patterns including or_methods, or_hosts, and label templating.
"""

import re
from typing import Any, Dict, List, Optional


def expand_template(template: str, config: Dict[str, Any]) -> str:
    """Expand ${variable} templates in strings."""
    if not isinstance(template, str):
        return template

    # Replace ${account_id}
    account_id = config.get("metadata", {}).get("account_id", "")
    template = template.replace("${account_id}", str(account_id))

    return template


def build_field_to_match(field: str, config: Dict[str, Any]) -> str:
    """Build field_to_match HCL block."""
    field_upper = field.upper()

    if field_upper == "BODY":
        oversize = config.get("oversize_handling", "CONTINUE")
        return f'''field_to_match {{
          body {{
            oversize_handling = "{oversize}"
          }}
        }}'''

    if field_upper == "QUERY_STRING":
        return '''field_to_match {
          query_string {}
        }'''

    if field_upper == "URI_PATH":
        return '''field_to_match {
          uri_path {}
        }'''

    if field_upper == "METHOD":
        return '''field_to_match {
          method {}
        }'''

    if field_upper == "SINGLE_HEADER":
        header_name = config.get("header_name", "").lower()
        return f'''field_to_match {{
          single_header {{
            name = "{header_name}"
          }}
        }}'''

    if field_upper == "ALL_QUERY_ARGUMENTS":
        return '''field_to_match {
          all_query_arguments {}
        }'''

    return '''field_to_match {
          body {}
        }'''


def build_text_transformations(transformations: Optional[List[Dict[str, Any]]]) -> str:
    """Build text_transformation HCL blocks."""
    if not transformations:
        return '''text_transformation {
          priority = 0
          type     = "NONE"
        }'''

    blocks = []
    for t in transformations:
        priority = t.get("priority", 0)
        trans_type = t.get("type", "NONE")
        blocks.append(f'''text_transformation {{
          priority = {priority}
          type     = "{trans_type}"
        }}''')

    return "\n        ".join(blocks)


def build_byte_match_statement(byte_match: Dict[str, Any], indent: int = 8) -> str:
    """Build a byte_match_statement HCL block."""
    ind = " " * indent
    field = byte_match.get("field", "BODY")
    search_string = byte_match.get("search_string", "")
    constraint = byte_match.get("positional_constraint", "CONTAINS")

    field_block = build_field_to_match(field, byte_match)
    transform_block = build_text_transformations(byte_match.get("text_transformations"))

    return f'''{ind}byte_match_statement {{
{ind}  search_string         = "{search_string}"
{ind}  positional_constraint = "{constraint}"
{ind}  {field_block}
{ind}  {transform_block}
{ind}}}'''


def build_sqli_match_statement(sqli_match: Dict[str, Any], indent: int = 8) -> str:
    """Build a sqli_match_statement HCL block.

    Supports sensitivity_level: LOW (fewer false positives) or HIGH (more aggressive).
    LOW is recommended to avoid false positives like WebKit form boundaries (----).
    """
    ind = " " * indent
    field = sqli_match.get("field", "BODY")
    sensitivity_level = sqli_match.get("sensitivity_level", "LOW")  # Default to LOW to reduce false positives

    field_block = build_field_to_match(field, sqli_match)
    transform_block = build_text_transformations(sqli_match.get("text_transformations"))

    return f'''{ind}sqli_match_statement {{
{ind}  sensitivity_level = "{sensitivity_level}"
{ind}  {field_block}
{ind}  {transform_block}
{ind}}}'''


def build_xss_match_statement(xss_match: Dict[str, Any], indent: int = 8) -> str:
    """Build a xss_match_statement HCL block."""
    ind = " " * indent
    field = xss_match.get("field", "BODY")

    field_block = build_field_to_match(field, xss_match)
    transform_block = build_text_transformations(xss_match.get("text_transformations"))

    return f'''{ind}xss_match_statement {{
{ind}  {field_block}
{ind}  {transform_block}
{ind}}}'''


def build_size_constraint_statement(size_constraint: Dict[str, Any], indent: int = 8) -> str:
    """Build a size_constraint_statement HCL block."""
    ind = " " * indent
    field = size_constraint.get("field", "BODY")
    operator = size_constraint.get("comparison_operator", "GT")
    size = size_constraint.get("size", 0)

    field_block = build_field_to_match(field, size_constraint)
    transform_block = build_text_transformations(size_constraint.get("text_transformations"))

    return f'''{ind}size_constraint_statement {{
{ind}  comparison_operator = "{operator}"
{ind}  size                = {size}
{ind}  {field_block}
{ind}  {transform_block}
{ind}}}'''


def build_regex_match_statement(regex_match: Dict[str, Any], indent: int = 8) -> str:
    """Build a regex_match_statement HCL block."""
    ind = " " * indent
    field = regex_match.get("field", "BODY")
    regex_string = regex_match.get("regex_string", "")

    field_block = build_field_to_match(field, regex_match)
    transform_block = build_text_transformations(regex_match.get("text_transformations"))

    return f'''{ind}regex_match_statement {{
{ind}  regex_string = "{regex_string}"
{ind}  {field_block}
{ind}  {transform_block}
{ind}}}'''


def build_label_match_statement(label_match: Dict[str, Any], config: Dict[str, Any], indent: int = 8) -> str:
    """Build a label_match_statement HCL block."""
    ind = " " * indent
    scope = label_match.get("scope", "LABEL")
    key = expand_template(label_match.get("key", ""), config)

    return f'''{ind}label_match_statement {{
{ind}  scope = "{scope}"
{ind}  key   = "{key}"
{ind}}}'''


def build_or_methods_statement(methods: List[str], indent: int = 8) -> str:
    """Build OR statement for multiple HTTP methods."""
    ind = " " * indent
    statements = []

    for method in methods:
        stmt = f'''{ind}  statement {{
{ind}    byte_match_statement {{
{ind}      search_string         = "{method.lower()}"
{ind}      positional_constraint = "EXACTLY"
{ind}      field_to_match {{
{ind}        method {{}}
{ind}      }}
{ind}      text_transformation {{
{ind}        priority = 0
{ind}        type     = "LOWERCASE"
{ind}      }}
{ind}    }}
{ind}  }}'''
        statements.append(stmt)

    return f'''{ind}or_statement {{
{chr(10).join(statements)}
{ind}}}'''


def build_or_hosts_statement(hosts: List[Dict[str, Any]], indent: int = 8) -> str:
    """Build OR statement for multiple hosts."""
    ind = " " * indent
    statements = []

    for host_def in hosts:
        host = host_def.get("host", "")
        match_type = host_def.get("match", "EXACTLY")

        stmt = f'''{ind}  statement {{
{ind}    byte_match_statement {{
{ind}      search_string         = "{host}"
{ind}      positional_constraint = "{match_type}"
{ind}      field_to_match {{
{ind}        single_header {{
{ind}          name = "host"
{ind}        }}
{ind}      }}
{ind}      text_transformation {{
{ind}        priority = 0
{ind}        type     = "LOWERCASE"
{ind}      }}
{ind}    }}
{ind}  }}'''
        statements.append(stmt)

    return f'''{ind}or_statement {{
{chr(10).join(statements)}
{ind}}}'''


def build_statement(statement: Dict[str, Any], config: Dict[str, Any], indent: int = 8) -> str:
    """Build a complete statement block recursively."""
    ind = " " * indent

    # Handle AND statement
    if "and" in statement:
        sub_statements = []
        for sub in statement["and"]:
            sub_stmt = build_statement(sub, config, indent + 2)
            sub_statements.append(f"{ind}  statement {{\n{sub_stmt}\n{ind}  }}")
        return f"{ind}and_statement {{\n" + "\n".join(sub_statements) + f"\n{ind}}}"

    # Handle OR statement
    if "or" in statement:
        sub_statements = []
        for sub in statement["or"]:
            sub_stmt = build_statement(sub, config, indent + 2)
            sub_statements.append(f"{ind}  statement {{\n{sub_stmt}\n{ind}  }}")
        return f"{ind}or_statement {{\n" + "\n".join(sub_statements) + f"\n{ind}}}"

    # Handle NOT statement
    if "not" in statement:
        sub_stmt = build_statement(statement["not"], config, indent + 2)
        return f"{ind}not_statement {{\n{ind}  statement {{\n{sub_stmt}\n{ind}  }}\n{ind}}}"

    # Handle or_methods shorthand
    if "or_methods" in statement:
        methods = statement["or_methods"]
        return build_or_methods_statement(methods, indent)

    # Handle or_hosts shorthand
    if "or_hosts" in statement:
        hosts_ref = statement["or_hosts"]
        if hosts_ref == "${allowed_hosts}":
            hosts = config.get("allowed_hosts", [])
        else:
            hosts = hosts_ref if isinstance(hosts_ref, list) else []
        return build_or_hosts_statement(hosts, indent)

    # Handle leaf statements
    if "byte_match" in statement:
        return build_byte_match_statement(statement["byte_match"], indent)

    if "sqli_match" in statement:
        return build_sqli_match_statement(statement["sqli_match"], indent)

    if "xss_match" in statement:
        return build_xss_match_statement(statement["xss_match"], indent)

    if "size_constraint" in statement:
        return build_size_constraint_statement(statement["size_constraint"], indent)

    if "regex_match" in statement:
        return build_regex_match_statement(statement["regex_match"], indent)

    if "label_match" in statement:
        return build_label_match_statement(statement["label_match"], config, indent)

    return ""


def build_visibility_config(name: str, indent: int = 4) -> str:
    """Build visibility_config HCL block."""
    ind = " " * indent
    metric_name = re.sub(r'[^a-zA-Z0-9]', '', name)
    return f'''{ind}visibility_config {{
{ind}  cloudwatch_metrics_enabled = true
{ind}  metric_name                = "{metric_name}"
{ind}  sampled_requests_enabled   = true
{ind}}}'''


def build_action(action: str, custom_response: Optional[Dict[str, Any]] = None, indent: int = 4) -> str:
    """Build action HCL block."""
    ind = " " * indent

    if action == "allow":
        return f"{ind}action {{\n{ind}  allow {{}}\n{ind}}}"
    elif action == "count":
        return f"{ind}action {{\n{ind}  count {{}}\n{ind}}}"
    elif action == "block":
        if custom_response:
            resp_code = custom_response.get("response_code", 403)
            body_key = custom_response.get("custom_response_body_key", "")
            return f'''{ind}action {{
{ind}  block {{
{ind}    custom_response {{
{ind}      response_code              = {resp_code}
{ind}      custom_response_body_key   = "{body_key}"
{ind}    }}
{ind}  }}
{ind}}}'''
        return f"{ind}action {{\n{ind}  block {{}}\n{ind}}}"

    return f"{ind}action {{\n{ind}  allow {{}}\n{ind}}}"


def build_rule_labels(label: Optional[str], namespace: Optional[str] = None, indent: int = 4) -> str:
    """Build rule_label HCL block."""
    if not label:
        return ""

    ind = " " * indent
    if namespace:
        full_label = f"{namespace}:{label}"
    else:
        full_label = label

    return f'''{ind}rule_label {{
{ind}  name = "{full_label}"
{ind}}}'''


def sanitize_resource_name(name: str) -> str:
    """Convert name to valid Terraform resource name."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)
