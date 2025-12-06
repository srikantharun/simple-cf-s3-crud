#!/usr/bin/env python3
"""
WAF Policy Generator - Main CLI Entry Point.
Converts YAML configuration to Terraform files and test cases.
"""

import sys
from pathlib import Path

import click
import yaml

from validators import WAFPolicyValidator
from terraform_builder import TerraformBuilder
from test_generator import TestGenerator


@click.command()
@click.option(
    "--config", "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to YAML configuration file"
)
@click.option(
    "--output", "-o",
    default="output",
    type=click.Path(),
    help="Output directory for generated files"
)
@click.option(
    "--validate-only", "-v",
    is_flag=True,
    help="Only validate the YAML configuration"
)
@click.option(
    "--tests-only", "-t",
    is_flag=True,
    help="Only generate test files (skip Terraform)"
)
@click.option(
    "--terraform-only", "-T",
    is_flag=True,
    help="Only generate Terraform files (skip tests)"
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    help="Enable debug output"
)
def main(config: str, output: str, validate_only: bool, tests_only: bool,
         terraform_only: bool, debug: bool) -> None:
    """
    WAF Policy Generator - Convert YAML to Terraform + Test Cases.

    Examples:
        python waf_generator.py --config configs/donut_v8.yaml --output ./output
        python waf_generator.py --config configs/donut_v8.yaml --validate-only
        python waf_generator.py --config configs/donut_v8.yaml --tests-only
    """
    # Load configuration
    try:
        with open(config) as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        click.echo(f"Error loading YAML file: {e}", err=True)
        sys.exit(1)

    # Validate
    validator = WAFPolicyValidator()
    is_valid = validator.validate(config_data)
    validator.print_results()

    if not is_valid:
        click.echo("\nConfiguration validation failed. Please fix errors above.", err=True)
        sys.exit(1)

    if validate_only:
        click.echo("\nValidation successful!")
        sys.exit(0)

    project = config_data.get("metadata", {}).get("project", "waf-policy")

    # Generate Terraform
    if not tests_only:
        click.echo("\nGenerating Terraform files...")
        terraform_builder = TerraformBuilder(config_data, debug=debug)
        terraform_builder.generate(output)
        click.echo(f"  -> {output}/{project}/terraform/")

    # Generate Tests
    if not terraform_only:
        test_defs = config_data.get("test_definitions", {})
        if test_defs:
            click.echo("\nGenerating test files...")
            test_generator = TestGenerator(config_data, debug=debug)
            test_generator.generate(output)
            click.echo(f"  -> {output}/{project}/tests/")
        else:
            click.echo("\nNo test_definitions found, skipping test generation.")

    # Summary
    click.echo(f"\nGeneration complete!")
    click.echo(f"\nNext steps:")
    if not tests_only:
        click.echo(f"  cd {output}/{project}/terraform")
        click.echo("  terraform init")
        click.echo("  terraform plan")
        click.echo("  terraform apply")

    if not terraform_only and test_defs:
        click.echo(f"\nRun tests:")
        click.echo(f"  cd {output}/{project}/tests")
        click.echo("  ./test_runner.sh")


if __name__ == "__main__":
    main()
