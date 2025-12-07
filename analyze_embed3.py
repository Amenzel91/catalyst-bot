#!/usr/bin/env python3
"""Analyze the embed structure from the log file to find Discord validation issues."""
import json

# Read the last embed_structure log entry
with open("data/logs/bot.jsonl", "r", encoding="utf-8") as f:
    lines = f.readlines()

for line in reversed(lines):
    if "embed_structure=" in line:
        log_entry = json.loads(line)
        # Extract the JSON from the message
        msg = log_entry["msg"]
        embed_json = msg.split("embed_structure=", 1)[1]
        embed = json.loads(embed_json)

        print(f"Fields count: {len(embed.get('fields', []))}")

        # Check fields array in detail
        errors_found = []
        for i, field in enumerate(embed.get("fields", [])):
            if not isinstance(field, dict):
                errors_found.append(f"Field {i}: Not a dict!")
                continue

            name = field.get("name")
            value = field.get("value")
            inline = field.get("inline")

            if name is None:
                errors_found.append(f"Field {i}: name is NULL!")
            if value is None:
                errors_found.append(f"Field {i}: value is NULL!")
            if inline is None:
                errors_found.append(f"Field {i}: inline is NULL!")
            if not isinstance(inline, bool):
                errors_found.append(
                    f"Field {i}: inline is not boolean (type: {type(inline).__name__})"
                )

        if errors_found:
            print("\nERRORS FOUND:")
            for err in errors_found:
                print(f"  - {err}")
        else:
            print("\nNo null values or type errors found in fields array!")

        # Check image field
        image = embed.get("image")
        if image:
            print(f"\nImage URL type: {type(image.get('url')).__name__}")
            if image.get("url") is None:
                print("  ERROR: image.url is NULL!")

        break
