"""
YAML validation module for WAF policy configurations.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class WAFPolicyValidator:
    """Validates WAF policy YAML configurations."""

    VALID_SCOPES = {"CLOUDFRONT", "REGIONAL"}
    VALID_ACTIONS = {"allow", "block", "count", "none"}
    VALID_RULE_TYPES = {"ip_set", "managed", "custom", "external", "module"}
    VALID_FIELDS = {
        "BODY", "JSON_BODY", "HEADERS", "COOKIES", "URI_PATH",
        "QUERY_STRING", "SINGLE_HEADER", "SINGLE_QUERY_ARGUMENT",
        "ALL_QUERY_ARGUMENTS", "METHOD"
    }
    VALID_POSITIONAL_CONSTRAINTS = {"EXACTLY", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "CONTAINS_WORD"}
    VALID_COMPARISON_OPERATORS = {"EQ", "NE", "LE", "LT", "GE", "GT"}
    VALID_TEXT_TRANSFORMATIONS = {
        "NONE", "COMPRESS_WHITE_SPACE", "HTML_ENTITY_DECODE", "LOWERCASE",
        "CMD_LINE", "URL_DECODE", "BASE64_DECODE", "HEX_DECODE",
        "NORMALIZE_PATH", "NORMALIZE_PATH_WIN", "REMOVE_NULLS", "URL_DECODE_UNI"
    }

    def __init__(self, schema_path: Optional[str] = None):
        """Initialize validator."""
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_yaml(self, config_path: str) -> Dict[str, Any]:
        """Load and parse YAML configuration file."""
        with open(config_path) as f:
            return yaml.safe_load(f)

    def validate(self, config: Dict[str, Any]) -> bool:
        """Validate configuration against schema and business rules."""
        self.errors = []
        self.warnings = []

        # Required sections
        if "version" not in config:
            self.errors.append("Missing required field: version")
        if "metadata" not in config:
            self.errors.append("Missing required field: metadata")
        if "settings" not in config:
            self.errors.append("Missing required field: settings")
        if "rule_groups" not in config:
            self.errors.append("Missing required field: rule_groups")

        if self.errors:
            return False

        # Validate sections
        self._validate_metadata(config.get("metadata", {}))
        self._validate_settings(config.get("settings", {}))
        self._validate_allowed_hosts(config.get("allowed_hosts", []))
        self._validate_rule_groups(config)
        self._validate_security_policy(config)
        self._validate_test_definitions(config.get("test_definitions", {}))

        return len(self.errors) == 0

    def _validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validate metadata section."""
        required = ["project", "policy_name", "account_id"]
        for field in required:
            if field not in metadata:
                self.errors.append(f"Missing required metadata field: {field}")

        if "account_id" in metadata:
            account_id = str(metadata["account_id"])
            if not account_id.isdigit() or len(account_id) != 12:
                self.warnings.append(f"Account ID '{account_id}' should be 12 digits")

    def _validate_settings(self, settings: Dict[str, Any]) -> None:
        """Validate settings section."""
        scope = settings.get("scope", "")
        if scope and scope not in self.VALID_SCOPES:
            self.errors.append(f"Invalid scope '{scope}'. Must be CLOUDFRONT or REGIONAL")

        default_action = settings.get("default_action", "")
        if default_action and default_action not in {"allow", "block", "count"}:
            self.errors.append(f"Invalid default_action '{default_action}'")

    def _validate_allowed_hosts(self, hosts: List[Dict[str, Any]]) -> None:
        """Validate allowed_hosts definitions."""
        for host in hosts:
            if "host" not in host:
                self.errors.append("allowed_hosts entry missing 'host' field")
            match_type = host.get("match", "EXACTLY")
            if match_type not in self.VALID_POSITIONAL_CONSTRAINTS:
                self.errors.append(f"Invalid match type '{match_type}' in allowed_hosts")

    def _validate_rule_groups(self, config: Dict[str, Any]) -> None:
        """Validate rule groups section."""
        rule_groups = config.get("rule_groups", {})
        orders = set()

        for name, group in rule_groups.items():
            # Validate order uniqueness
            order = group.get("order")
            if order is not None:
                if order in orders:
                    self.errors.append(f"Duplicate order {order} in rule_groups")
                orders.add(order)

            # Validate by type
            rule_type = group.get("type", "")
            if rule_type not in self.VALID_RULE_TYPES:
                self.errors.append(f"Invalid rule type '{rule_type}' in {name}")

            if rule_type == "ip_set":
                self._validate_ip_set_group(name, group)
            elif rule_type == "managed":
                self._validate_managed_group(name, group)
            elif rule_type == "custom":
                self._validate_custom_group(name, group, config)
            elif rule_type == "external":
                self._validate_external_group(name, group)
            elif rule_type == "module":
                self._validate_module_group(name, group)

    def _validate_ip_set_group(self, name: str, group: Dict[str, Any]) -> None:
        """Validate IP set rule group."""
        if "ip_addresses" not in group:
            self.errors.append(f"Rule group '{name}': ip_set must have ip_addresses")

        ip_addresses = group.get("ip_addresses", [])
        for ip in ip_addresses:
            if not self._is_valid_cidr(ip):
                self.errors.append(f"Rule group '{name}': Invalid CIDR '{ip}'")

    def _validate_managed_group(self, name: str, group: Dict[str, Any]) -> None:
        """Validate managed rule group."""
        if "managed_rule_group" not in group:
            self.errors.append(f"Rule group '{name}': managed type requires managed_rule_group")

    def _validate_external_group(self, name: str, group: Dict[str, Any]) -> None:
        """Validate external rule group (references common module ARN)."""
        # Must have either arn_variable or arn_variable_count/arn_variable_block
        has_single = "arn_variable" in group
        has_split = "arn_variable_count" in group or "arn_variable_block" in group

        if not has_single and not has_split:
            self.errors.append(f"Rule group '{name}': external type requires arn_variable or arn_variable_count/arn_variable_block")

    def _validate_module_group(self, name: str, group: Dict[str, Any]) -> None:
        """Validate module rule group (references terraform module)."""
        if "module_source" not in group:
            self.errors.append(f"Rule group '{name}': module type requires module_source")

    def _validate_custom_group(self, name: str, group: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Validate custom rule group."""
        rules = group.get("rules", [])
        if not rules:
            self.errors.append(f"Rule group '{name}': custom type must have rules")

        for rule in rules:
            self._validate_rule(name, rule, config)

    def _validate_rule(self, group_name: str, rule: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Validate a single rule."""
        rule_name = rule.get("name", "unknown")

        if "name" not in rule:
            self.errors.append(f"Rule in '{group_name}' missing name")
        if "action" not in rule:
            self.errors.append(f"Rule '{rule_name}' missing action")
        if "statement" not in rule:
            self.errors.append(f"Rule '{rule_name}' missing statement")

        action = rule.get("action", "")
        if action and action not in self.VALID_ACTIONS:
            self.errors.append(f"Rule '{rule_name}': Invalid action '{action}'")

        statement = rule.get("statement", {})
        if statement:
            self._validate_statement(group_name, rule_name, statement, config)

    def _validate_statement(self, group_name: str, rule_name: str,
                           statement: Dict[str, Any], config: Dict[str, Any]) -> None:
        """Recursively validate a statement."""
        # Handle compound statements
        if "and" in statement:
            for sub_stmt in statement["and"]:
                self._validate_statement(group_name, rule_name, sub_stmt, config)
            return

        if "or" in statement:
            for sub_stmt in statement["or"]:
                self._validate_statement(group_name, rule_name, sub_stmt, config)
            return

        if "not" in statement:
            self._validate_statement(group_name, rule_name, statement["not"], config)
            return

        # Handle special shorthand statements
        if "or_methods" in statement:
            methods = statement["or_methods"]
            if not isinstance(methods, list):
                self.errors.append(f"Rule '{rule_name}': or_methods must be a list")

        if "or_hosts" in statement:
            hosts_ref = statement["or_hosts"]
            if hosts_ref == "${allowed_hosts}":
                if not config.get("allowed_hosts"):
                    self.warnings.append(f"Rule '{rule_name}': references allowed_hosts but none defined")

        # Validate specific statement types
        if "byte_match" in statement:
            self._validate_byte_match(group_name, rule_name, statement["byte_match"])
        elif "sqli_match" in statement:
            self._validate_match_statement(group_name, rule_name, statement["sqli_match"])
        elif "xss_match" in statement:
            self._validate_match_statement(group_name, rule_name, statement["xss_match"])
        elif "size_constraint" in statement:
            self._validate_size_constraint(group_name, rule_name, statement["size_constraint"])
        elif "regex_match" in statement:
            self._validate_regex_match(group_name, rule_name, statement["regex_match"])
        elif "label_match" in statement:
            self._validate_label_match(group_name, rule_name, statement["label_match"])

    def _validate_byte_match(self, group_name: str, rule_name: str,
                            byte_match: Dict[str, Any]) -> None:
        """Validate byte_match statement."""
        field = byte_match.get("field", "")
        if field and field not in self.VALID_FIELDS:
            self.errors.append(f"Rule '{rule_name}': Invalid field '{field}'")

        if field == "SINGLE_HEADER" and not byte_match.get("header_name"):
            self.errors.append(f"Rule '{rule_name}': SINGLE_HEADER requires header_name")

        constraint = byte_match.get("positional_constraint", "")
        if constraint and constraint not in self.VALID_POSITIONAL_CONSTRAINTS:
            self.errors.append(f"Rule '{rule_name}': Invalid positional_constraint '{constraint}'")

    def _validate_match_statement(self, group_name: str, rule_name: str,
                                  match: Dict[str, Any]) -> None:
        """Validate sqli_match or xss_match statement."""
        field = match.get("field", "")
        if field and field not in self.VALID_FIELDS:
            self.errors.append(f"Rule '{rule_name}': Invalid field '{field}'")

    def _validate_size_constraint(self, group_name: str, rule_name: str,
                                  constraint: Dict[str, Any]) -> None:
        """Validate size_constraint statement."""
        field = constraint.get("field", "")
        if field and field not in self.VALID_FIELDS:
            self.errors.append(f"Rule '{rule_name}': Invalid field '{field}'")

        operator = constraint.get("comparison_operator", "")
        if operator and operator not in self.VALID_COMPARISON_OPERATORS:
            self.errors.append(f"Rule '{rule_name}': Invalid comparison_operator '{operator}'")

        size = constraint.get("size")
        if size is not None and not isinstance(size, int):
            self.errors.append(f"Rule '{rule_name}': size must be an integer")

    def _validate_regex_match(self, group_name: str, rule_name: str,
                             regex: Dict[str, Any]) -> None:
        """Validate regex_match statement."""
        field = regex.get("field", "")
        if field and field not in self.VALID_FIELDS:
            self.errors.append(f"Rule '{rule_name}': Invalid field '{field}'")

        regex_string = regex.get("regex_string", "")
        if regex_string:
            try:
                re.compile(regex_string)
            except re.error as e:
                self.errors.append(f"Rule '{rule_name}': Invalid regex '{regex_string}': {e}")

    def _validate_label_match(self, group_name: str, rule_name: str,
                             label_match: Dict[str, Any]) -> None:
        """Validate label_match statement."""
        scope = label_match.get("scope", "")
        if scope and scope not in {"LABEL", "NAMESPACE"}:
            self.errors.append(f"Rule '{rule_name}': Invalid label scope '{scope}'")

    def _validate_security_policy(self, config: Dict[str, Any]) -> None:
        """Validate security policy references."""
        security_policy = config.get("security_policy", {})
        rule_groups = config.get("rule_groups", {})

        first_groups = security_policy.get("first_rule_groups", [])
        last_groups = security_policy.get("last_rule_groups", [])

        for group_name in first_groups + last_groups:
            if group_name not in rule_groups:
                self.errors.append(f"Security policy references undefined rule group '{group_name}'")

    def _validate_test_definitions(self, test_defs: Dict[str, Any]) -> None:
        """Validate test definitions."""
        if not test_defs:
            return

        test_suites = test_defs.get("test_suites", [])
        for suite in test_suites:
            if "name" not in suite:
                self.errors.append("Test suite missing name")

            tests = suite.get("tests", [])
            for test in tests:
                if "id" not in test:
                    self.errors.append(f"Test in suite '{suite.get('name')}' missing id")
                if "request" not in test:
                    self.errors.append(f"Test '{test.get('id')}' missing request")

    def _is_valid_cidr(self, cidr: str) -> bool:
        """Check if string is a valid CIDR notation."""
        import ipaddress
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError:
            return False

    def get_errors(self) -> List[str]:
        """Return list of validation errors."""
        return self.errors

    def get_warnings(self) -> List[str]:
        """Return list of validation warnings."""
        return self.warnings

    def print_results(self) -> None:
        """Print validation results."""
        if self.errors:
            print("\nValidation Errors:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\nValidation Warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.errors and not self.warnings:
            print("\nValidation passed with no errors or warnings")
        elif not self.errors:
            print("\nValidation passed with warnings")
