#!/usr/bin/env python3
"""
Convert SEC company_tickers.json to NDJSON format for Catalyst Bot.

CRITICAL FIX: Field Name Correction
===================================
This script converts the SEC's official company tickers JSON file to NDJSON format
with the CORRECT field name that matches the bot's code expectations.

PROBLEM:
    SEC provides:     {"cik_str": 320193, "ticker": "AAPL", ...}
    Code expects:     {"cik": "0000320193", "ticker": "AAPL", ...}
                              ↑
                       Different field name!

    The code at src/catalyst_bot/ticker_map.py:79 does:
        cik = str(obj.get("cik") or "").strip()

    When NDJSON has "cik_str", obj.get("cik") returns None → 0 entries loaded!

SOLUTION:
    This script renames "cik_str" → "cik" and pads to 10 digits with leading zeros.

PREREQUISITES:
    1. Download SEC data first (see instructions below)
    2. Python 3.7+ installed
    3. File: company_tickers_raw.json must exist in same directory

OUTPUT:
    - Creates: company_tickers.ndjson (10,000+ entries)
    - Format: {"cik": "0000320193", "ticker": "AAPL", "title": "Apple Inc."}
    - One JSON object per line (NDJSON format)

USAGE:
    python3 convert_sec_tickers.py

AUTHOR: Generated for Catalyst Bot CIK mapping fix
DATE: 2025-12-11
"""

import json
import sys
from pathlib import Path


def convert():
    """Convert SEC company_tickers.json to NDJSON with correct field names."""

    input_file = "company_tickers_raw.json"
    output_file = "company_tickers.ndjson"

    print("=" * 80)
    print("SEC Company Tickers → NDJSON Converter")
    print("=" * 80)
    print()

    # Step 1: Validate input file exists
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ ERROR: {input_file} not found!")
        print()
        print("Please download SEC data first:")
        print()
        print('  curl -H "User-Agent: catalyst-bot/1.0 (your-email@example.com)" \\')
        print("       https://www.sec.gov/files/company_tickers.json \\")
        print("       -o company_tickers_raw.json")
        print()
        sys.exit(1)

    # Step 2: Load SEC JSON
    print(f"📂 Reading {input_file}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in {input_file}")
        print(f"   {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to read {input_file}")
        print(f"   {str(e)}")
        sys.exit(1)

    print(f"✅ Loaded {len(data)} entries from SEC")
    print()

    # Step 3: Validate data format
    if not isinstance(data, dict):
        print(f"❌ ERROR: Expected dict, got {type(data).__name__}")
        sys.exit(1)

    # Step 4: Show sample input
    if data:
        sample_key = list(data.keys())[0]
        sample_entry = data[sample_key]
        print("📊 Sample SEC entry (BEFORE conversion):")
        print(f"   {json.dumps(sample_entry, indent=2)}")
        print()
        print("   ⚠️  Note: Uses 'cik_str' field (WRONG for our code)")
        print()

    # Step 5: Convert to NDJSON with CORRECT field name
    print("🔄 Converting to NDJSON format...")
    print("   - Renaming 'cik_str' → 'cik'")
    print("   - Padding CIKs to 10 digits (e.g., 320193 → 0000320193)")
    print("   - Uppercasing tickers")
    print()

    count = 0
    skipped = 0

    # Backup existing file if it exists
    output_path = Path(output_file)
    if output_path.exists():
        backup_path = output_path.with_suffix(".ndjson.backup")
        print(f"📦 Backing up existing {output_file} → {backup_path.name}")
        output_path.rename(backup_path)
        print()

    with open(output_file, "w", encoding="utf-8") as f:
        for entry in data.values():
            # Extract fields from SEC format
            cik_str = str(entry.get("cik_str", "")).strip()
            ticker = entry.get("ticker", "").strip()
            title = entry.get("title", "").strip()

            # Validate required fields
            if not cik_str or not ticker:
                skipped += 1
                continue

            # Pad CIK to 10 digits (SEC standard format)
            cik_padded = cik_str.zfill(10)

            # CRITICAL: Use "cik" field name to match ticker_map.py line 79
            # This is the key fix - the code does obj.get("cik"), not obj.get("cik_str")
            record = {"cik": cik_padded, "ticker": ticker.upper(), "title": title}

            # Write as NDJSON (one JSON object per line)
            f.write(json.dumps(record) + "\n")
            count += 1

    print("✅ Conversion complete!")
    print(f"   - Wrote {count:,} entries to {output_file}")
    if skipped > 0:
        print(f"   - Skipped {skipped} entries (missing CIK or ticker)")
    print()

    # Step 6: Show sample output
    with open(output_file, "r", encoding="utf-8") as f:
        first_line = f.readline()
        sample_record = json.loads(first_line)

    print("📊 Sample NDJSON entry (AFTER conversion):")
    print(f"   {json.dumps(sample_record, indent=2)}")
    print()
    print("   ✅ Note: Uses 'cik' field (CORRECT for our code)")
    print()

    # Step 7: Validation checks
    print("🔍 Validation Checks:")
    print("   ✅ Field name: 'cik' (not 'cik_str')")
    print(f"   ✅ CIK format: {sample_record['cik']} (10 digits, zero-padded)")
    print(f"   ✅ Ticker format: {sample_record['ticker']} (uppercase)")
    print(f"   ✅ Entry count: {count:,} entries")
    print()

    # Step 8: Next steps
    print("=" * 80)
    print("✅ CONVERSION SUCCESSFUL!")
    print("=" * 80)
    print()
    print("Next steps:")
    print()
    print("1. Verify output:")
    print(f"   head -3 {output_file}")
    print()
    print("2. Commit to repository:")
    print(f"   git add {output_file}")
    print(
        '   git commit -m "fix: populate CIK mappings (10k+ entries, correct field name)"'
    )
    print("   git push")
    print()
    print("3. Clear SQLite cache (forces rebuild from NDJSON):")
    print("   rm -f data/tickers.db")
    print()
    print("4. Test CIK lookup:")
    print("   python -m catalyst_bot.runner --once")
    print("   grep 'ticker_bootstrap_done' data/logs/bot.jsonl | tail -1")
    print(f"   # Expected: ticker_bootstrap_done rows={count}")
    print()


if __name__ == "__main__":
    convert()
