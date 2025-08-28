#!/usr/bin/env python3
"""
tools/deep_scan.py

Make a compact map of
- where alerts are emitted (Discord/webhook calls, alerts.* helpers, stray prints)
- where tickers are extracted / sanitized
- where classifiers / analyzers / rules live

Writes:
  scan/alerts_map.json
  scan/alerts_map.md
"""

from __future__ import annotations

import ast
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
OUTDIR = os.path.join(ROOT, "scan")
os.makedirs(OUTDIR, exist_ok=True)

ALERT_FN_PREFIXES = ("alerts.", "alert_bus.", "discord_alerts.")
WEBHOOK_SUBSTRS = ("discord.com/api/webhooks", "hooks.slack.com")
PRINT_ALERT_SUBSTRS = ("[ALERT]", "ALERT:", "alert:")

KEY_FN_NAMES = {
    "extract_ticker",
    "sanitize_ticker",
    "classify",
    "classify_title",
    "analyze",
    "emit_alert",
    "send_alert_safe",
    "post_discord_json",
}

KEYWORD_HITS = (
    "analy",
    "classif",
    "signal",
    "rule",
    "screener",
    "ingest",
    "filing",
    "finviz",
)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def safe_parse(src: str) -> Optional[ast.AST]:
    try:
        return ast.parse(src)
    except Exception:
        return None


def find_calls(tree: ast.AST) -> List[Tuple[int, str]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn_name = None
            if isinstance(node.func, ast.Attribute):
                parts = []
                cur = node.func
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                parts.reverse()
                fn_name = ".".join(parts)
            elif isinstance(node.func, ast.Name):
                fn_name = node.func.id
            else:
                fn_name = None
            if not fn_name:
                continue

            literal_args = []
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    literal_args.append(a.value)

            out.append(
                (
                    node.lineno,
                    fn_name + (" " + " ".join(literal_args) if literal_args else ""),
                )
            )
    return out


def sniff_file(path: str) -> Dict[str, Any]:
    rel = os.path.relpath(path, ROOT)
    src = read_text(path)
    tree = safe_parse(src)
    d: Dict[str, Any] = {
        "path": rel,
        "alerts": [],
        "webhooks": [],
        "prints": [],
        "key_defs": [],
        "key_calls": [],
        "keyword_flags": [],
    }
    if tree is None:
        d["parse_error"] = True
        return d

    # defs
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name in KEY_FN_NAMES or any(
                k in node.name.lower() for k in KEYWORD_HITS
            ):
                d["key_defs"].append({"name": node.name, "line": node.lineno})
        if isinstance(node, ast.ClassDef):
            if any(k in node.name.lower() for k in KEYWORD_HITS):
                d["key_defs"].append(
                    {"name": f"class {node.name}", "line": node.lineno}
                )

    # calls
    for lineno, sig in find_calls(tree):
        lower = sig.lower()
        if any(lower.startswith(pref) for pref in ALERT_FN_PREFIXES):
            d["alerts"].append({"line": lineno, "call": sig})
        if any(sub in sig for sub in WEBHOOK_SUBSTRS):
            d["webhooks"].append({"line": lineno, "call": sig})
        if "print" == lower.split()[0]:
            if any(s in sig for s in PRINT_ALERT_SUBSTRS):
                d["prints"].append({"line": lineno, "call": sig})
        base = lower.split()[0]
        if base in KEY_FN_NAMES:
            d["key_calls"].append({"line": lineno, "call": sig})

    low_src = src.lower()
    for kw in KEYWORD_HITS:
        if kw in low_src:
            d["keyword_flags"].append(kw)

    return d


def walk_py(root: str) -> List[str]:
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        if any(
            skip in dirpath
            for skip in (".git", ".venv", "env", "build", "dist", "__pycache__")
        ):
            continue
        for fn in filenames:
            if fn.endswith(".py"):
                paths.append(os.path.join(dirpath, fn))
    return paths


def main():
    files = walk_py(ROOT)
    rows = [sniff_file(p) for p in files]
    interesting = [
        r
        for r in rows
        if r.get("alerts")
        or r.get("webhooks")
        or r.get("prints")
        or r.get("key_defs")
        or r.get("key_calls")
    ]
    interesting.sort(key=lambda r: r["path"])

    with open(os.path.join(OUTDIR, "alerts_map.json"), "w", encoding="utf-8") as f:
        json.dump(interesting, f, indent=2)

    md_lines = ["# Alert & Analyzer Map", ""]
    for r in interesting:
        md_lines.append(f"## {r['path']}")
        if r.get("parse_error"):
            md_lines.append("- parse_error ✅")
        if r["key_defs"]:
            md_lines.append("- Key defs:")
            for d in r["key_defs"]:
                md_lines.append(f"  - L{d['line']}: `{d['name']}`")
        if r["alerts"]:
            md_lines.append("- Alerts calls:")
            for a in r["alerts"]:
                md_lines.append(f"  - L{a['line']}: `{a['call']}`")
        if r["webhooks"]:
            md_lines.append("- Raw webhook-ish calls:")
            for a in r["webhooks"]:
                md_lines.append(f"  - L{a['line']}: `{a['call']}`")
        if r["prints"]:
            md_lines.append("- Print-based alerts:")
            for a in r["prints"]:
                md_lines.append(f"  - L{a['line']}: `{a['call']}`")
        if r["key_calls"]:
            md_lines.append("- Key calls:")
            for a in r["key_calls"]:
                md_lines.append(f"  - L{a['line']}: `{a['call']}`")
        if r["keyword_flags"]:
            md_lines.append(f"- Keywords: {', '.join(sorted(set(r['keyword_flags'])))}")
        md_lines.append("")
    with open(os.path.join(OUTDIR, "alerts_map.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Wrote {len(interesting)} files -> {OUTDIR}/alerts_map.(json|md)")


if __name__ == "__main__":
    main()
