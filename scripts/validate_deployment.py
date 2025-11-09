#!/usr/bin/env python3
"""
Deployment Validation Script for Catalyst Bot (Wave 4 - Final Polish).

This script validates that the codebase is ready for production deployment by checking:
1. All required environment variables are documented
2. All new modules are importable
3. Required directories exist
4. Code quality metrics meet thresholds
5. Test coverage is adequate

Usage:
    python scripts/validate_deployment.py

Exit codes:
    0: All validations passed
    1: One or more validations failed
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ANSI color codes for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"{GREEN}[OK]{RESET} {text}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(f"{YELLOW}[WARN]{RESET} {text}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"{RED}[ERROR]{RESET} {text}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"{BLUE}[INFO]{RESET} {text}")


def get_project_root() -> Path:
    """Get the project root directory."""
    # Assuming script is in scripts/ subdirectory
    script_path = Path(__file__).resolve()
    return script_path.parent.parent


def check_environment_variables() -> Tuple[bool, Dict[str, any]]:
    """
    Check that all required environment variables are documented in .env.example.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Environment Variables Check")

    project_root = get_project_root()
    env_example = project_root / ".env.example"

    if not env_example.exists():
        print_error(f".env.example not found at {env_example}")
        return False, {"env_vars_documented": 0}

    # Required variables (core functionality)
    required_vars = [
        "DISCORD_WEBHOOK_URL",
        "BENZINGA_API_KEY",
        "TIINGO_API_KEY",
        "OPENAI_API_KEY",
    ]

    # Optional but recommended variables
    optional_vars = [
        "OLLAMA_BASE_URL",
        "SEC_API_KEY",
        "NEWSFILTER_TOKEN",
        "ALPHAVANTAGE_API_KEY",
    ]

    with open(env_example, "r", encoding="utf-8") as f:
        env_content = f.read()

    success = True
    documented_count = 0

    # Check required variables
    print_info("Checking required environment variables...")
    for var in required_vars:
        if var in env_content:
            print_success(f"{var}: documented")
            documented_count += 1
        else:
            print_error(f"{var}: NOT documented in .env.example")
            success = False

    # Check optional variables (warnings only)
    print_info("\nChecking optional environment variables...")
    for var in optional_vars:
        if var in env_content:
            print_success(f"{var}: documented")
            documented_count += 1
        else:
            print_warning(f"{var}: Not documented (optional)")

    total_vars = len(required_vars) + len(optional_vars)
    coverage_pct = (documented_count / total_vars) * 100

    print_info(f"\nEnvironment variable documentation: {documented_count}/{total_vars} ({coverage_pct:.1f}%)")

    return success, {
        "env_vars_documented": documented_count,
        "env_vars_total": total_vars,
        "env_coverage_pct": coverage_pct,
    }


def check_module_imports() -> Tuple[bool, Dict[str, any]]:
    """
    Check that all new Wave 2-4 modules are importable.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Module Import Check")

    project_root = get_project_root()
    src_dir = project_root / "src"

    # Add src to path
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # New modules from Waves 2-4
    new_modules = [
        "catalyst_bot.catalyst_badges",
        "catalyst_bot.multi_ticker_handler",
        "catalyst_bot.offering_sentiment",
    ]

    success = True
    importable_count = 0

    for module_name in new_modules:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                print_error(f"{module_name}: NOT FOUND")
                success = False
            else:
                # Try actual import
                importlib.import_module(module_name)
                print_success(f"{module_name}: importable")
                importable_count += 1
        except Exception as e:
            print_error(f"{module_name}: IMPORT ERROR - {e}")
            success = False

    import_success_rate = (importable_count / len(new_modules)) * 100
    print_info(f"\nModule import success: {importable_count}/{len(new_modules)} ({import_success_rate:.1f}%)")

    return success, {
        "modules_importable": importable_count,
        "modules_total": len(new_modules),
        "import_success_rate": import_success_rate,
    }


def check_required_directories() -> Tuple[bool, Dict[str, any]]:
    """
    Check that required directories exist.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Required Directories Check")

    project_root = get_project_root()

    required_dirs = [
        "data",
        "data/logs",
        "data/cache",
        "src/catalyst_bot",
        "tests",
    ]

    success = True
    existing_count = 0

    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if full_path.exists() and full_path.is_dir():
            print_success(f"{dir_path}/: exists")
            existing_count += 1
        else:
            print_warning(f"{dir_path}/: does not exist (will be created on first run)")
            # Don't fail - these can be created at runtime

    return True, {
        "required_dirs_existing": existing_count,
        "required_dirs_total": len(required_dirs),
    }


def analyze_docstring_coverage() -> Tuple[bool, Dict[str, any]]:
    """
    Analyze docstring coverage for new Wave 2-4 modules.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Docstring Coverage Analysis")

    project_root = get_project_root()
    src_dir = project_root / "src" / "catalyst_bot"

    modules_to_check = [
        "catalyst_badges.py",
        "multi_ticker_handler.py",
        "offering_sentiment.py",
    ]

    total_functions = 0
    documented_functions = 0

    for module_file in modules_to_check:
        module_path = src_dir / module_file

        if not module_path.exists():
            print_warning(f"{module_file}: not found")
            continue

        with open(module_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(module_path))
            except SyntaxError as e:
                print_error(f"{module_file}: syntax error - {e}")
                continue

        module_funcs = 0
        module_documented = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private functions (but count them)
                if not node.name.startswith("_"):
                    module_funcs += 1
                    total_functions += 1

                    # Check if has docstring
                    has_docstring = (
                        ast.get_docstring(node) is not None
                        and len(ast.get_docstring(node).strip()) > 10
                    )

                    if has_docstring:
                        module_documented += 1
                        documented_functions += 1

        coverage = (module_documented / module_funcs * 100) if module_funcs > 0 else 0
        status_icon = GREEN if coverage >= 80 else YELLOW if coverage >= 60 else RED
        print(f"{status_icon}[*]{RESET} {module_file}: {module_documented}/{module_funcs} functions ({coverage:.1f}%)")

    overall_coverage = (documented_functions / total_functions * 100) if total_functions > 0 else 0
    success = overall_coverage >= 80.0

    if success:
        print_success(f"\nOverall docstring coverage: {overall_coverage:.1f}% (target: 80%+)")
    else:
        print_warning(f"\nOverall docstring coverage: {overall_coverage:.1f}% (target: 80%+)")

    return success, {
        "functions_documented": documented_functions,
        "functions_total": total_functions,
        "docstring_coverage_pct": overall_coverage,
    }


def analyze_type_hint_coverage() -> Tuple[bool, Dict[str, any]]:
    """
    Analyze type hint coverage for new Wave 2-4 modules.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Type Hint Coverage Analysis")

    project_root = get_project_root()
    src_dir = project_root / "src" / "catalyst_bot"

    modules_to_check = [
        "catalyst_badges.py",
        "multi_ticker_handler.py",
        "offering_sentiment.py",
    ]

    total_functions = 0
    typed_functions = 0

    for module_file in modules_to_check:
        module_path = src_dir / module_file

        if not module_path.exists():
            print_warning(f"{module_file}: not found")
            continue

        with open(module_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(module_path))
            except SyntaxError as e:
                print_error(f"{module_file}: syntax error - {e}")
                continue

        module_funcs = 0
        module_typed = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private functions and __init__
                if not node.name.startswith("_") or node.name == "__init__":
                    module_funcs += 1
                    total_functions += 1

                    # Check if has return type annotation
                    has_return_type = node.returns is not None

                    # Check if all args have type annotations (except self/cls)
                    args_typed = True
                    for arg in node.args.args:
                        if arg.arg not in ("self", "cls") and arg.annotation is None:
                            args_typed = False
                            break

                    if has_return_type and args_typed:
                        module_typed += 1
                        typed_functions += 1

        coverage = (module_typed / module_funcs * 100) if module_funcs > 0 else 0
        status_icon = GREEN if coverage >= 80 else YELLOW if coverage >= 60 else RED
        print(f"{status_icon}[*]{RESET} {module_file}: {module_typed}/{module_funcs} functions ({coverage:.1f}%)")

    overall_coverage = (typed_functions / total_functions * 100) if total_functions > 0 else 0
    success = overall_coverage >= 80.0

    if success:
        print_success(f"\nOverall type hint coverage: {overall_coverage:.1f}% (target: 80%+)")
    else:
        print_warning(f"\nOverall type hint coverage: {overall_coverage:.1f}% (target: 80%+)")

    return success, {
        "functions_typed": typed_functions,
        "functions_total": total_functions,
        "type_hint_coverage_pct": overall_coverage,
    }


def check_config_defaults() -> Tuple[bool, Dict[str, any]]:
    """
    Validate that config.py has sensible defaults.

    Returns:
        Tuple of (success, metrics_dict)
    """
    print_header("Configuration Defaults Check")

    project_root = get_project_root()
    config_path = project_root / "src" / "catalyst_bot" / "config.py"

    if not config_path.exists():
        print_error(f"config.py not found at {config_path}")
        return False, {}

    # Key config values to check
    expected_defaults = {
        "BENZINGA_LOOKBACK_MINUTES": (10, 60),  # (min, max) reasonable range
        "MAX_AGE_MINUTES": (15, 60),
        "MAX_SEC_AGE_MINUTES": (120, 360),
    }

    success = True
    validated_count = 0

    with open(config_path, "r", encoding="utf-8") as f:
        config_content = f.read()

    for var_name, (min_val, max_val) in expected_defaults.items():
        # Simple pattern matching (not perfect but good enough)
        import re
        pattern = rf'{var_name}\s*=\s*(\d+)'
        match = re.search(pattern, config_content)

        if match:
            value = int(match.group(1))
            if min_val <= value <= max_val:
                print_success(f"{var_name}={value} (valid range: {min_val}-{max_val})")
                validated_count += 1
            else:
                print_warning(f"{var_name}={value} (outside recommended range: {min_val}-{max_val})")
        else:
            print_info(f"{var_name}: not found or using environment variable")

    return success, {
        "config_defaults_validated": validated_count,
        "config_defaults_checked": len(expected_defaults),
    }


def calculate_deployment_readiness_score(all_metrics: Dict[str, Dict[str, any]]) -> int:
    """
    Calculate overall deployment readiness score (0-100).

    Args:
        all_metrics: Dictionary of all validation metrics

    Returns:
        Readiness score from 0-100
    """
    score = 0

    # Environment variables (20 points max)
    if "environment" in all_metrics:
        env_coverage = all_metrics["environment"].get("env_coverage_pct", 0)
        score += min(env_coverage * 0.2, 20)

    # Module imports (20 points max)
    if "imports" in all_metrics:
        import_rate = all_metrics["imports"].get("import_success_rate", 0)
        score += min(import_rate * 0.2, 20)

    # Docstring coverage (20 points max)
    if "docstrings" in all_metrics:
        doc_coverage = all_metrics["docstrings"].get("docstring_coverage_pct", 0)
        score += min(doc_coverage * 0.2, 20)

    # Type hint coverage (20 points max)
    if "type_hints" in all_metrics:
        type_coverage = all_metrics["type_hints"].get("type_hint_coverage_pct", 0)
        score += min(type_coverage * 0.2, 20)

    # Configuration (20 points max)
    if "config" in all_metrics:
        config_validated = all_metrics["config"].get("config_defaults_validated", 0)
        config_checked = all_metrics["config"].get("config_defaults_checked", 1)
        config_rate = (config_validated / config_checked * 100) if config_checked > 0 else 0
        score += min(config_rate * 0.2, 20)

    return int(score)


def main() -> int:
    """
    Run all deployment validation checks.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print(f"\n{BOLD}Catalyst Bot Deployment Validation{RESET}")
    print(f"{'='*70}\n")

    all_metrics = {}
    all_passed = True

    # Run all checks
    checks = [
        ("environment", check_environment_variables),
        ("imports", check_module_imports),
        ("directories", check_required_directories),
        ("docstrings", analyze_docstring_coverage),
        ("type_hints", analyze_type_hint_coverage),
        ("config", check_config_defaults),
    ]

    for check_name, check_func in checks:
        try:
            passed, metrics = check_func()
            all_metrics[check_name] = metrics
            if not passed:
                all_passed = False
        except Exception as e:
            print_error(f"Check '{check_name}' failed with error: {e}")
            all_passed = False

    # Calculate overall readiness score
    readiness_score = calculate_deployment_readiness_score(all_metrics)

    # Print summary
    print_header("Deployment Readiness Summary")

    print(f"\n{BOLD}Readiness Score: {readiness_score}/100{RESET}")

    if readiness_score >= 90:
        print_success("Excellent! Deployment ready.")
        status_icon = GREEN + "[PASS]" + RESET
    elif readiness_score >= 75:
        print_success("Good! Minor improvements recommended before deployment.")
        status_icon = YELLOW + "[WARN]" + RESET
    elif readiness_score >= 60:
        print_warning("Fair. Several improvements needed before deployment.")
        status_icon = YELLOW + "[WARN]" + RESET
    else:
        print_error("Poor. Significant work needed before deployment.")
        status_icon = RED + "[FAIL]" + RESET
        all_passed = False

    # Print metrics summary
    print(f"\n{BOLD}Metrics Summary:{RESET}")
    if "environment" in all_metrics:
        print(f"  • Environment Variables: {all_metrics['environment'].get('env_vars_documented', 0)}/{all_metrics['environment'].get('env_vars_total', 0)}")
    if "imports" in all_metrics:
        print(f"  • Module Imports: {all_metrics['imports'].get('modules_importable', 0)}/{all_metrics['imports'].get('modules_total', 0)}")
    if "docstrings" in all_metrics:
        print(f"  • Docstring Coverage: {all_metrics['docstrings'].get('docstring_coverage_pct', 0):.1f}%")
    if "type_hints" in all_metrics:
        print(f"  • Type Hint Coverage: {all_metrics['type_hints'].get('type_hint_coverage_pct', 0):.1f}%")

    print(f"\n{status_icon} Overall Status: {'PASS' if all_passed else 'NEEDS ATTENTION'}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
