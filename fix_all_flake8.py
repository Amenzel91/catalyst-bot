#!/usr/bin/env python3
"""
Comprehensive script to fix all flake8 errors.
"""

import re
from pathlib import Path

def fix_file(filepath, fixes):
    """Apply fixes to a file"""
    content = filepath.read_text(encoding='utf-8')
    lines = content.splitlines()

    for fix in fixes:
        fix_type = fix['type']

        if fix_type == 'bare_except':
            line_num = fix['line']
            if 0 < line_num <= len(lines):
                lines[line_num - 1] = lines[line_num - 1].replace('except:', 'except Exception:')

        elif fix_type == 'unused_var':
            line_num = fix['line']
            var_name = fix['var']
            if 0 < line_num <= len(lines):
                line = lines[line_num - 1]
                if f'{var_name} =' in line:
                    lines[line_num - 1] = line.replace(f'{var_name} =', '_ =')

        elif fix_type == 'f_string':
            line_num = fix['line']
            if 0 < line_num <= len(lines):
                line = lines[line_num - 1]
                if 'f"' in line and '{' not in line:
                    lines[line_num - 1] = line.replace('f"', '"')
                elif "f'" in line and '{' not in line:
                    lines[line_num - 1] = line.replace("f'", "'")

        elif fix_type == 'add_import_requests':
            # Add import requests at top
            import_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    import_idx = i + 1
            if import_idx > 0 and 'import requests' not in '\n'.join(lines):
                lines.insert(import_idx, 'import requests')

        elif fix_type == 'add_timezone_import':
            # Add timezone to datetime import
            for i, line in enumerate(lines):
                if 'from datetime import' in line and 'timezone' not in line:
                    lines[i] = line.rstrip() + ', timezone'
                    break

        elif fix_type == 'module_import_top':
            # Move import to top
            line_num = fix['line']
            if 0 < line_num <= len(lines):
                import_line = lines[line_num - 1]
                # Remove from current location
                lines.pop(line_num - 1)
                # Find first non-comment, non-docstring line
                insert_idx = 0
                in_docstring = False
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        in_docstring = not in_docstring
                    elif not in_docstring and not stripped.startswith('#') and stripped:
                        if not (stripped.startswith('import ') or stripped.startswith('from ')):
                            insert_idx = i
                            break
                lines.insert(insert_idx, import_line)

        elif fix_type == 'long_line_manual':
            line_num = fix['line']
            replacement = fix['replacement']
            if 0 < line_num <= len(lines):
                lines[line_num - 1] = replacement

    filepath.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Fixed {filepath.name}')

# Base directory
BASE = Path('src/catalyst_bot')

# Fix alerts.py
fix_file(BASE / 'alerts.py', [
    {'type': 'unused_var', 'line': 1736, 'var': 'ticker'},
])

# Fix runner.py - add requests import
fix_file(BASE / 'runner.py', [
    {'type': 'add_import_requests'},
])

# Fix sentiment_sources.py - add timezone import
fix_file(BASE / 'sentiment_sources.py', [
    {'type': 'add_timezone_import'},
])

# Fix test_closed_loop.py - move import to top
fix_file(Path('test_closed_loop.py'), [
    {'type': 'module_import_top', 'line': 19},
    {'type': 'f_string', 'line': 95},
    {'type': 'f_string', 'line': 107},
    {'type': 'f_string', 'line': 109},
    {'type': 'f_string', 'line': 116},
    {'type': 'f_string', 'line': 118},
    {'type': 'f_string', 'line': 124},
    {'type': 'f_string', 'line': 127},
    {'type': 'f_string', 'line': 167},
    {'type': 'f_string', 'line': 169},
    {'type': 'f_string', 'line': 173},
    {'type': 'f_string', 'line': 175},
    {'type': 'f_string', 'line': 178},
])

print('\nAll fixes applied!')
print('Please run pre-commit manually to fix long lines automatically.')
