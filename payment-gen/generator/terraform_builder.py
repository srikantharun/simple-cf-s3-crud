"""
Terraform HCL builder for WAF policies.
Generates valid Terraform files that pass terraform fmt and validate.
Supports aws_fms_policy with external, custom, and module rule groups.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rule_builder import (
    build_statement,
    build_visibility_config,
    build_action,
    build_rule_labels,
    sanitize_resource_name,
    expand_template,
)


class TerraformBuilder:
    """Builds Terraform HCL files from WAF policy configuration."""

    def __init__(self, config: Dict[str, Any], debug: bool = False):
        self.config = config
        self.debug = debug
        self.metadata = config.get("metadata", {})
        self.settings = config.get("settings", {})
        self.rule_groups = config.get("rule_groups", {})
        self.security_policy = config.get("security_policy", {})
        self.custom_response_bodies = config.get("custom_response_bodies", {})

        self.project = self.metadata.get("project", "waf-policy")
        self.policy_name = self.metadata.get("policy_name", f"{self.project}-policy")
        self.policy_version = self.metadata.get("policy_version", "v1").replace("v", "")
        self.account_id = str(self.metadata.get("account_id", ""))
        self.service_name = self.project.replace("v8", "").replace("v", "")

    def generate(self, output_dir: str) -> None:
        """Generate all Terraform files."""
        terraform_dir = Path(output_dir) / self.project / "terraform"
        terraform_dir.mkdir(parents=True, exist_ok=True)

        self._log(f"Generating Terraform files in {terraform_dir}")

        self._generate_versions_tf(terraform_dir)
        self._generate_main_tf(terraform_dir)
        self._generate_variables_tf(terraform_dir)
        self._generate_modules_tf(terraform_dir)
        self._generate_rule_groups_tf(terraform_dir)
        self._generate_fms_policy_tf(terraform_dir)
        self._generate_outputs_tf(terraform_dir)

        self._log("Terraform generation complete!")

    def _log(self, message: str) -> None:
        """Print debug message if debug mode enabled."""
        if self.debug:
            print(f"[DEBUG] {message}")

    def _generate_versions_tf(self, output_dir: Path) -> None:
        """Generate versions.tf file."""
        content = '''terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}
'''
        (output_dir / "versions.tf").write_text(content)

    def _generate_main_tf(self, output_dir: Path) -> None:
        """Generate main.tf (providers and locals) file."""
        scope = self.settings.get("scope", "REGIONAL")

        content = f'''# WAF Policy Configuration
# Scope: {scope}

locals {{
  scope = "{scope}"
}}

data "aws_region" "current" {{}}
data "aws_caller_identity" "current" {{}}

'''
        if scope == "CLOUDFRONT":
            content += '''# CloudFront WAF must be deployed in us-east-1
provider "aws" {
  region = "us-east-1"
  alias  = "waf"
}

provider "aws" {
  region = var.aws_region
}
'''
        else:
            content += '''provider "aws" {
  region = var.aws_region
}
'''
        (output_dir / "main.tf").write_text(content)

    def _generate_variables_tf(self, output_dir: Path) -> None:
        """Generate variables.tf file with external ARN inputs."""
        fms_admin_account = self.settings.get("fms_admin_account", "")

        # Base variables
        content = f'''# =============================================================================
# Base Variables
# =============================================================================

variable "aws_region" {{
  description = "AWS region"
  type        = string
  default     = "ap-east-1"
}}

variable "environment" {{
  description = "Environment name"
  type        = string
  default     = "{self.metadata.get('environment', 'production')}"
}}

variable "project" {{
  description = "Project name"
  type        = string
  default     = "{self.project}"
}}

variable "service_name" {{
  description = "Service name for FMS policy"
  type        = string
  default     = "{self.service_name}"
}}

variable "policy_version" {{
  description = "Policy version number"
  type        = string
  default     = "{self.policy_version}"
}}

variable "account_id" {{
  description = "AWS Account ID"
  type        = string
  default     = "{self.account_id}"
}}

variable "default_account" {{
  description = "Default account for FMS policy"
  type        = string
  default     = "{self.account_id}"
}}

variable "fms_admin_account" {{
  description = "FMS Admin Account ID"
  type        = string
  default     = "{fms_admin_account}"
}}

variable "owasp_rule_label_namespace" {{
  description = "OWASP rule label namespace"
  type        = string
  default     = "abcd:cyber:custom:owasp"
}}

variable "tags" {{
  description = "Additional tags"
  type        = map(string)
  default     = {{}}
}}

# =============================================================================
# External Rule Group ARN Variables (Common Modules)
# =============================================================================

'''
        # Generate variables for external rule groups
        for name, group in self.rule_groups.items():
            if group.get("type") != "external":
                continue

            description = group.get("description", f"ARN for {name}")

            # Single ARN variable
            if "arn_variable" in group:
                var_name = group["arn_variable"]
                content += f'''variable "{var_name}" {{
  description = "{description}"
  type        = string
}}

'''
            # Separate ARN variables for count and block
            if "arn_variable_count" in group:
                var_name = group["arn_variable_count"]
                content += f'''variable "{var_name}" {{
  description = "{description} (count policy)"
  type        = string
}}

'''
            if "arn_variable_block" in group:
                var_name = group["arn_variable_block"]
                content += f'''variable "{var_name}" {{
  description = "{description} (block policy)"
  type        = string
}}

'''

        (output_dir / "variables.tf").write_text(content)

    def _generate_modules_tf(self, output_dir: Path) -> None:
        """Generate modules.tf file for catch-all and other module references."""
        modules_hcl = []

        for name, group in self.rule_groups.items():
            if group.get("type") != "module":
                continue

            resource_name = self._get_resource_name(name, group)
            module_source = group.get("module_source", "")
            module_params = group.get("module_params", {})

            # Build module parameters
            params_hcl = []
            for param_name, param_value in module_params.items():
                # Check if it's a reference (starts with aws_ or module.)
                if isinstance(param_value, str) and (param_value.startswith("aws_") or param_value.startswith("module.")):
                    params_hcl.append(f'  {param_name:20} = {param_value}')
                else:
                    params_hcl.append(f'  {param_name:20} = "{param_value}"')

            params_str = "\n".join(params_hcl)

            module_hcl = f'''module "{resource_name}" {{
  source            = "{module_source}"
{params_str}
  scope             = local.scope
  tags              = var.tags
  owasp_rule_label_namespace = var.owasp_rule_label_namespace
}}
'''
            modules_hcl.append(module_hcl)

        if modules_hcl:
            content = "# =============================================================================\n"
            content += "# Custom Catch Modules\n"
            content += "# =============================================================================\n\n"
            content += "\n".join(modules_hcl)
        else:
            content = "# No module references defined\n"

        (output_dir / "modules.tf").write_text(content)

    def _get_resource_name(self, name: str, group: Dict[str, Any]) -> str:
        """Get Terraform resource name from group config.

        Uses the 'name' field (sanitized) if available, otherwise falls back to YAML key.
        This allows engineers to have flexible naming.
        """
        group_name = group.get("name", name)
        # Expand ${project} in name
        group_name = group_name.replace("${project}", self.project)
        return sanitize_resource_name(group_name)

    def _generate_rule_groups_tf(self, output_dir: Path) -> None:
        """Generate waf_rule_groups.tf file for custom rule groups only."""
        scope = self.settings.get("scope", "REGIONAL")
        provider = 'provider = aws.waf\n  ' if scope == "CLOUDFRONT" else ""

        rule_groups_hcl = []

        for name, group in self.rule_groups.items():
            if group.get("type") != "custom":
                continue

            resource_name = self._get_resource_name(name, group)
            group_name = group.get("name", name)
            # Expand ${project} in name
            group_name = group_name.replace("${project}", self.project)
            capacity = group.get("capacity", 100)
            description = group.get("description", "")
            namespace = group.get("namespace", "custom")

            rules_hcl = self._build_custom_rules(group, namespace)

            rule_group = f'''resource "aws_wafv2_rule_group" "{resource_name}" {{
  {provider}name        = "{group_name}"
  description = "{description}"
  scope       = local.scope
  capacity    = {capacity}

{rules_hcl}

  visibility_config {{
    cloudwatch_metrics_enabled = true
    metric_name                = "{sanitize_resource_name(group_name)}"
    sampled_requests_enabled   = true
  }}

  tags = merge(var.tags, {{
    Name        = "{group_name}"
    Environment = var.environment
    Project     = var.project
  }})
}}
'''
            rule_groups_hcl.append(rule_group)

        if rule_groups_hcl:
            content = "# =============================================================================\n"
            content += "# Custom Rule Groups (Project-Specific)\n"
            content += "# =============================================================================\n\n"
            content += "\n".join(rule_groups_hcl)
        else:
            content = "# No custom rule groups defined\n"

        (output_dir / "waf_rule_groups.tf").write_text(content)

    def _build_custom_rules(self, group: Dict[str, Any], namespace: str) -> str:
        """Build all rules for a custom rule group."""
        rules = group.get("rules", [])
        rules_hcl = []

        for rule in rules:
            rule_hcl = self._build_single_rule(rule, namespace)
            rules_hcl.append(rule_hcl)

        return "\n".join(rules_hcl)

    def _build_single_rule(self, rule: Dict[str, Any], namespace: str) -> str:
        """Build a single rule HCL block."""
        name = rule.get("name", "rule")
        priority = rule.get("priority", 0)
        action = rule.get("action", "count")
        label = rule.get("label")
        custom_response = rule.get("custom_response")
        statement = rule.get("statement", {})

        action_hcl = build_action(action, custom_response, indent=4)
        statement_hcl = build_statement(statement, self.config, indent=6)
        visibility_hcl = build_visibility_config(name, indent=4)

        label_hcl = ""
        if label:
            label_hcl = build_rule_labels(label, namespace, indent=4)

        return f'''  rule {{
    name     = "{name}"
    priority = {priority}

{action_hcl}

    statement {{
{statement_hcl}
    }}
{label_hcl}
{visibility_hcl}
  }}'''

    def _generate_fms_policy_tf(self, output_dir: Path) -> None:
        """Generate fms_policy.tf file with aws_fms_policy resources."""
        scope = self.settings.get("scope", "REGIONAL")
        resource_type = self.settings.get("resource_type", "AWS::CloudFront::Distribution")
        auto_remediation = self.settings.get("auto_remediation", True)
        body_size_limit = self.settings.get("body_size_limit", 65536)
        body_size_kb = f"KB_{body_size_limit // 1024}" if body_size_limit >= 1024 else "KB_16"

        # Get FMS policy resource names from config (with ${project} expansion)
        fms_count_name = self.settings.get("fms_policy_count_resource_name", "count")
        fms_count_name = sanitize_resource_name(fms_count_name.replace("${project}", self.project))
        fms_block_name = self.settings.get("fms_policy_block_resource_name", "block")
        fms_block_name = sanitize_resource_name(fms_block_name.replace("${project}", self.project))

        # Store for use in outputs
        self._fms_count_resource_name = fms_count_name
        self._fms_block_resource_name = fms_block_name

        # Build preProcessRuleGroups for count policy
        pre_process_count = self._build_pre_process_rule_groups(mode="count")

        # Build preProcessRuleGroups for block policy
        pre_process_block = self._build_pre_process_rule_groups(mode="block")

        # Get depends_on list
        depends_on_count = self._build_depends_on(mode="count")
        depends_on_block = self._build_depends_on(mode="block")

        content = f'''# =============================================================================
# AWS FMS WAFv2 Policies
# Scope: {scope}
# Resource Type: {resource_type}
# =============================================================================

# =============================================================================
# FMS Policy: Count Mode (Monitoring)
# =============================================================================

resource "aws_fms_policy" "{fms_count_name}" {{
  name                               = "custom_${{var.service_name}}_global_count_version_${{var.policy_version}}"
  resource_type                      = "{resource_type}"
  delete_all_policy_resources        = true
  delete_unused_fm_managed_resources = true
  exclude_resource_tags              = true
  remediation_enabled                = false

  resource_tags = {{
    "FMManagedWebACLWAFV2-custom_${{var.service_name}}_global_count" = "v${{var.policy_version}}"
  }}

  security_service_policy_data {{
    type = "WAFV2"

    managed_service_data = jsonencode({{
      type                       = "WAFV2"
      customRequestHandling      = null
      customResponse             = null
      loggingConfiguration       = null
      optimizeUnassociatedWebACL = false

      associationConfig = {{
        requestBody = {{
          {scope} = {{
            defaultSizeInspectionLimit = "{body_size_kb}"
          }}
        }}
      }}

      preProcessRuleGroups = {pre_process_count}

      postProcessRuleGroups = []

      defaultAction = {{
        type = "ALLOW"
      }}

      overrideCustomerWebACLAssociation       = false
      sampledRequestsEnabledForDefaultActions = false
    }})
  }}

  include_map {{
    account = [var.default_account]
  }}

  lifecycle {{
    ignore_changes = [include_map, tags]
  }}

{depends_on_count}
}}

# =============================================================================
# FMS Policy: Block Mode (Enforcement)
# =============================================================================

resource "aws_fms_policy" "{fms_block_name}" {{
  name                               = "custom_${{var.service_name}}_global_block_version_${{var.policy_version}}"
  resource_type                      = "{resource_type}"
  delete_all_policy_resources        = true
  delete_unused_fm_managed_resources = true
  exclude_resource_tags              = false
  remediation_enabled                = {"true" if auto_remediation else "false"}

  resource_tags = {{
    "FMManagedWebACLWAFV2-custom_${{var.service_name}}_global_block" = "v${{var.policy_version}}"
  }}

  security_service_policy_data {{
    type = "WAFV2"

    managed_service_data = jsonencode({{
      type                       = "WAFV2"
      customRequestHandling      = null
      customResponse             = null
      loggingConfiguration       = null
      optimizeUnassociatedWebACL = false

      associationConfig = {{
        requestBody = {{
          {scope} = {{
            defaultSizeInspectionLimit = "{body_size_kb}"
          }}
        }}
      }}

      preProcessRuleGroups = {pre_process_block}

      postProcessRuleGroups = []

      defaultAction = {{
        type = "ALLOW"
      }}

      overrideCustomerWebACLAssociation       = false
      sampledRequestsEnabledForDefaultActions = false
    }})
  }}

  include_map {{
    account = [var.default_account]
  }}

  lifecycle {{
    ignore_changes = [include_map, tags]
  }}

{depends_on_block}
}}
'''
        (output_dir / "fms_policy.tf").write_text(content)

    def _build_pre_process_rule_groups(self, mode: str = "block") -> str:
        """Build preProcessRuleGroups array for FMS policy."""
        rule_groups = []

        # Sort rule groups by order
        sorted_groups = sorted(
            [(name, group) for name, group in self.rule_groups.items()],
            key=lambda x: x[1].get("order", 999)
        )

        for name, group in sorted_groups:
            rule_type = group.get("type")
            resource_name = self._get_resource_name(name, group)

            # Check if this rule group should be included in this mode
            if mode == "count" and group.get("include_in_count") == False:
                continue

            # Get override action for this mode
            override_action_key = f"override_action_{mode}"
            override_type = group.get(override_action_key, "NONE")

            # Build rule action overrides if present
            rule_action_overrides = None
            overrides_key = f"rule_action_overrides_{mode}"
            if overrides_key in group:
                rule_action_overrides = []
                for override in group[overrides_key]:
                    rule_action_overrides.append({
                        "name": override["name"],
                        "actionToUse": {
                            override["action"]: {}
                        }
                    })

            if rule_type == "external":
                # Get ARN variable name
                if mode == "count" and "arn_variable_count" in group:
                    arn_var = group["arn_variable_count"]
                elif mode == "block" and "arn_variable_block" in group:
                    arn_var = group["arn_variable_block"]
                else:
                    arn_var = group.get("arn_variable", "")

                if not arn_var:
                    continue

                entry = {
                    "ruleGroupType": "RuleGroup",
                    "ruleGroupArn": f"${{var.{arn_var}}}",
                    "sampledRequestsEnabled": True,
                    "excludeRules": [],
                    "managedRuleGroupIdentifier": None,
                    "overrideAction": {
                        "type": override_type
                    }
                }
                if rule_action_overrides:
                    entry["ruleActionOverrides"] = rule_action_overrides

                rule_groups.append(("var", arn_var, entry))

            elif rule_type == "custom":
                arn_ref = f"aws_wafv2_rule_group.{resource_name}.arn"
                entry = {
                    "ruleGroupType": "RuleGroup",
                    "ruleGroupArn": f"${{{arn_ref}}}",
                    "sampledRequestsEnabled": True,
                    "excludeRules": [],
                    "managedRuleGroupIdentifier": None,
                    "overrideAction": {
                        "type": override_type
                    }
                }
                rule_groups.append(("resource", arn_ref, entry))

            elif rule_type == "module":
                output_arn = group.get("output_arn", "arn")
                arn_ref = f"module.{resource_name}.{output_arn}"
                entry = {
                    "ruleGroupType": "RuleGroup",
                    "ruleGroupArn": f"${{{arn_ref}}}",
                    "sampledRequestsEnabled": True,
                    "excludeRules": [],
                    "managedRuleGroupIdentifier": None,
                    "overrideAction": {
                        "type": override_type
                    }
                }
                rule_groups.append(("module", arn_ref, entry))

        # Build the output
        if not rule_groups:
            return "[]"

        output_lines = ["["]
        for i, (ref_type, ref_name, entry) in enumerate(rule_groups):
            entry_str = self._format_rule_group_entry(entry)
            comma = "," if i < len(rule_groups) - 1 else ""
            output_lines.append(f"        {entry_str}{comma}")
        output_lines.append("      ]")

        return "\n".join(output_lines)

    def _format_rule_group_entry(self, entry: Dict[str, Any]) -> str:
        """Format a single rule group entry for FMS policy."""
        lines = ["{"]

        lines.append(f'          ruleGroupType              = "{entry["ruleGroupType"]}"')
        lines.append(f'          ruleGroupArn               = {entry["ruleGroupArn"]}')
        lines.append(f'          sampledRequestsEnabled     = {"true" if entry["sampledRequestsEnabled"] else "false"}')
        lines.append(f'          excludeRules               = []')
        lines.append(f'          managedRuleGroupIdentifier = null')
        lines.append(f'          overrideAction = {{')
        lines.append(f'            type = "{entry["overrideAction"]["type"]}"')
        lines.append(f'          }}')

        if "ruleActionOverrides" in entry:
            lines.append(f'          ruleActionOverrides = [')
            for override in entry["ruleActionOverrides"]:
                action_type = list(override["actionToUse"].keys())[0]
                lines.append(f'            {{')
                lines.append(f'              name = "{override["name"]}"')
                lines.append(f'              actionToUse = {{')
                lines.append(f'                {action_type} = {{}}')
                lines.append(f'              }}')
                lines.append(f'            }},')
            lines.append(f'          ]')

        lines.append("        }")
        return "\n".join(lines)

    def _build_depends_on(self, mode: str = "block") -> str:
        """Build depends_on block for FMS policy."""
        depends = []

        for name, group in self.rule_groups.items():
            resource_name = self._get_resource_name(name, group)
            rule_type = group.get("type")

            # Skip if not included in this mode
            if mode == "count" and group.get("include_in_count") == False:
                continue

            if rule_type == "custom":
                depends.append(f"aws_wafv2_rule_group.{resource_name}")
            elif rule_type == "module":
                depends.append(f"module.{resource_name}")

        if not depends:
            return ""

        depends_str = ",\n    ".join(depends)
        return f'''  depends_on = [
    {depends_str}
  ]'''

    def _generate_outputs_tf(self, output_dir: Path) -> None:
        """Generate outputs.tf file."""
        # Check if we have any custom rule groups
        has_custom_rules = any(g.get("type") == "custom" for g in self.rule_groups.values())
        has_modules = any(g.get("type") == "module" for g in self.rule_groups.values())

        content = '''# =============================================================================
# Outputs
# =============================================================================

'''
        if has_custom_rules:
            content += '''# Custom Rule Group Outputs
output "rule_group_arns" {
  description = "ARNs of all custom rule groups"
  value = {
    for k, v in aws_wafv2_rule_group : k => v.arn
  }
}

'''

        if has_modules:
            # Generate module outputs
            for name, group in self.rule_groups.items():
                if group.get("type") != "module":
                    continue
                resource_name = self._get_resource_name(name, group)
                output_arn = group.get("output_arn", "arn")
                content += f'''output "{resource_name}_arn" {{
  description = "ARN of {name} module"
  value       = module.{resource_name}.{output_arn}
}}

'''

        # Get FMS policy resource names
        fms_count_name = getattr(self, '_fms_count_resource_name', 'count')
        fms_block_name = getattr(self, '_fms_block_resource_name', 'block')

        content += f'''# FMS Policy Outputs
output "fms_policy_count_id" {{
  description = "The ID of the FMS count policy"
  value       = aws_fms_policy.{fms_count_name}.id
}}

output "fms_policy_count_arn" {{
  description = "The ARN of the FMS count policy"
  value       = aws_fms_policy.{fms_count_name}.arn
}}

output "fms_policy_block_id" {{
  description = "The ID of the FMS block policy"
  value       = aws_fms_policy.{fms_block_name}.id
}}

output "fms_policy_block_arn" {{
  description = "The ARN of the FMS block policy"
  value       = aws_fms_policy.{fms_block_name}.arn
}}
'''
        (output_dir / "outputs.tf").write_text(content)
