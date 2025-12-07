#!/usr/bin/env python3
"""Analyze the embed structure from the log file to find Discord validation issues."""
import json

# Read the last embed_structure log entry
with open("data/logs/bot.jsonl", "r") as f:
    lines = f.readlines()

for line in reversed(lines):
    if "embed_structure=" in line:
        log_entry = json.loads(line)
        # Extract the JSON from the message
        msg = log_entry["msg"]
        embed_json = msg.split("embed_structure=", 1)[1]
        embed = json.loads(embed_json)

        print("=== EMBED STRUCTURE ANALYSIS ===\n")
        print(f"Top-level keys: {list(embed.keys())}")
        print(f"Fields count: {len(embed.get('fields', []))}")
        print()

        # Check for None/null values at top level
        print("=== TOP-LEVEL VALUES ===")
        for key, value in embed.items():
            if key == "fields":
                continue
            print(f"{key}: {value!r} (type: {type(value).__name__})")
            if value is None:
                print(f"  ^^^ WARNING: {key} is NULL!")
        print()

        # Check fields array
        print("=== FIELDS ARRAY (first 10) ===")
        for i, field in enumerate(embed.get("fields", [])[:10]):
            print(f"Field {i}:")
            for k, v in field.items():
                print(f"  {k}: {v!r} (type: {type(v).__name__})")
                if v is None:
                    print(f"    ^^^ WARNING: field[{i}].{k} is NULL!")

        break
