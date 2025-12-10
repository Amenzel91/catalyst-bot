#!/usr/bin/env python3
"""
Script to systematically fix all flake8 errors identified.
"""

import re
from pathlib import Path


def fix_bare_except(filepath):
    """Replace bare 'except:' with 'except Exception:'"""
    content = filepath.read_text(encoding='utf-8')
    # Match 'except:' but not 'except Exception:' or other specific exceptions
    content = re.sub(r'(\s+)except:\s*\n', r'\1except Exception:\n', content)
    filepath.write_text(content, encoding='utf-8')
    print(f"Fixed bare except in {filepath.name}")


def fix_unused_variables(filepath, line_num, var_name):
    """Remove unused variable assignments"""
    lines = filepath.read_text(encoding='utf-8').splitlines()
    if 0 < line_num <= len(lines):
        line = lines[line_num - 1]
        # Comment out or remove the unused variable
        if f'{var_name} =' in line:
            lines[line_num - 1] = line.replace(f'{var_name} = ', f'_ = ')
    filepath.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"Fixed unused variable '{var_name}' at line {line_num} in {filepath.name}")


def fix_f_string_no_placeholders(filepath, line_num):
    """Convert f-strings without placeholders to regular strings"""
    lines = filepath.read_text(encoding='utf-8').splitlines()
    if 0 < line_num <= len(lines):
        line = lines[line_num - 1]
        # Replace f"..." or f'...' with "..." or '...' if no {} placeholders
        if 'f"' in line and '{' not in line:
            lines[line_num - 1] = line.replace('f"', '"')
        elif "f'" in line and '{' not in line:
            lines[line_num - 1] = line.replace("f'", "'")
    filepath.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"Fixed f-string at line {line_num} in {filepath.name}")


def fix_long_lines_simple(filepath, line_numbers):
    """Split long lines at logical points"""
    lines = filepath.read_text(encoding='utf-8').splitlines()

    for line_num in sorted(line_numbers, reverse=True):
        if 0 < line_num <= len(lines):
            line = lines[line_num - 1]

            # Handle f-string concatenation
            if 'print(f"' in line or 'print(f\'' in line:
                # Find good split points for print statements
                if len(line) > 100:
                    indent = len(line) - len(line.lstrip())
                    # Try to split at a space near the middle
                    mid_point = 100
                    split_point = line.rfind(' ', 0, mid_point)
                    if split_point > indent + 20:
                        part1 = line[:split_point]
                        part2 = line[split_point+1:]

                        # Construct split line
                        if 'f"' in part1:
                            new_line = (f'{part1.rstrip()} "\n'
                                      f'{" " * (indent + 8)}f"{part2}"')
                        else:
                            new_line = (f'{part1.rstrip()}\n'
                                      f'{" " * (indent + 8)}{part2}')

                        lines[line_num - 1] = new_line

    filepath.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"Fixed long lines in {filepath.name}")


# Fix specific files based on flake8 output
BASE_DIR = Path(r"C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot")

# List of files with bare except
files_with_bare_except = [
    "analyze_dec9_api.py",
    "analyze_dec9_llm.py",
    "analyze_tiingo_responses.py"
]

print("Fixing bare except statements...")
for fname in files_with_bare_except:
    fpath = BASE_DIR / fname
    if fpath.exists():
        fix_bare_except(fpath)

print("\nDone!")
