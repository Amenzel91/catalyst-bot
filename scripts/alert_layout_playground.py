#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alert Layout Playground
=======================

Interactive tool for designing and testing Discord alert embed layouts.
Allows live editing of embed fields, before/after comparison, and saving
custom layout templates as JSON.

Features:
- Interactive CLI menu for editing embed fields
- Real-time preview of changes
- Before/after comparison mode
- Save/load layout templates
- Test layouts with real Discord webhooks
- Export templates for use in production

Usage:
    # Start interactive playground
    python scripts/alert_layout_playground.py

    # Load a saved template
    python scripts/alert_layout_playground.py --load templates/custom_layout.json

    # Test a template without interaction
    python scripts/alert_layout_playground.py --template templates/custom_layout.json --test
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "replace")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

import requests

from src.catalyst_bot.config import get_settings


# Default template structure
DEFAULT_TEMPLATE = {
    "name": "Default Alert Layout",
    "description": "Standard catalyst alert layout",
    "embed": {
        "title": "[TICKER] Catalyst Headline Goes Here",
        "url": "https://example.com",
        "color": 0x00FF00,
        "fields": [
            {
                "name": "💰 Price Action",
                "value": "$2.50 (↑ +25.00%)\nPrev: $2.00",
                "inline": True,
            },
            {
                "name": "📊 Volume",
                "value": "1.5M (RVol: 5.0x)\nAvg: 300K",
                "inline": True,
            },
            {
                "name": "📈 Score",
                "value": "8.5/10\nSentiment: 0.85 (Bullish)",
                "inline": True,
            },
            {
                "name": "🔍 Analysis",
                "value": "Strong catalyst with high conviction. Key metrics exceed thresholds.",
                "inline": False,
            },
            {
                "name": "Source",
                "value": "BusinessWire",
                "inline": True,
            },
            {
                "name": "Tickers",
                "value": "TICKER",
                "inline": False,
            },
        ],
        "footer": {"text": "Catalyst-Bot"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    },
}

# Color presets
COLOR_PRESETS = {
    "green": 0x00FF00,
    "blue": 0x0099FF,
    "red": 0xFF0000,
    "orange": 0xFF9900,
    "purple": 0x9900FF,
    "yellow": 0xFFFF00,
    "gray": 0x808080,
}


class EmbedPlayground:
    """Interactive embed layout editor."""

    def __init__(self, template: Optional[Dict] = None):
        """Initialize playground with a template."""
        self.template = template or DEFAULT_TEMPLATE.copy()
        self.original_template = json.loads(json.dumps(self.template))
        self.settings = get_settings()

    def display_embed(self, embed: Dict, title: str = "Current Layout"):
        """Display embed structure in readable format."""
        print(f"\n{'=' * 70}")
        print(f"  {title}")
        print('=' * 70)
        print(f"\nTitle: {embed.get('title', 'N/A')}")
        print(f"URL: {embed.get('url', 'N/A')}")
        print(f"Color: 0x{embed.get('color', 0):06X}")

        fields = embed.get("fields", [])
        print(f"\nFields ({len(fields)}):")
        for i, field in enumerate(fields, 1):
            inline_str = " [inline]" if field.get("inline", False) else ""
            print(f"\n  {i}. {field.get('name', 'N/A')}{inline_str}")
            value = field.get("value", "N/A")
            # Truncate long values for display
            if len(value) > 100:
                value = value[:97] + "..."
            print(f"     {value}")

        footer = embed.get("footer", {})
        if footer:
            print(f"\nFooter: {footer.get('text', 'N/A')}")

        print('=' * 70)

    def compare_embeds(self):
        """Show before/after comparison."""
        print("\n" + "=" * 140)
        print("  BEFORE/AFTER COMPARISON")
        print("=" * 140)

        original = self.original_template["embed"]
        current = self.template["embed"]

        # Side by side comparison
        print(f"\n{'ORIGINAL':<70} | {'CURRENT':<70}")
        print("-" * 140)

        # Compare titles
        orig_title = original.get("title", "")[:65]
        curr_title = current.get("title", "")[:65]
        print(f"{orig_title:<70} | {curr_title:<70}")
        print("-" * 140)

        # Compare fields
        orig_fields = original.get("fields", [])
        curr_fields = current.get("fields", [])
        max_fields = max(len(orig_fields), len(curr_fields))

        for i in range(max_fields):
            orig_field = orig_fields[i] if i < len(orig_fields) else {}
            curr_field = curr_fields[i] if i < len(curr_fields) else {}

            orig_name = orig_field.get("name", "---")[:30]
            curr_name = curr_field.get("name", "---")[:30]

            orig_value = orig_field.get("value", "")[:35]
            curr_value = curr_field.get("value", "")[:35]

            # Highlight changes
            changed = orig_field != curr_field
            marker = " *" if changed else ""

            print(f"{orig_name:<30} {orig_value:<35} | {curr_name:<30} {curr_value:<35}{marker}")

        print("=" * 140)
        print("* = Changed")

    def edit_title(self):
        """Edit embed title."""
        current = self.template["embed"].get("title", "")
        print(f"\nCurrent title: {current}")
        new_title = input("New title (or press Enter to keep): ").strip()
        if new_title:
            self.template["embed"]["title"] = new_title
            print("✓ Title updated")

    def edit_color(self):
        """Edit embed color."""
        current = self.template["embed"].get("color", 0)
        print(f"\nCurrent color: 0x{current:06X}")
        print("\nPresets:")
        for name, value in COLOR_PRESETS.items():
            print(f"  {name}: 0x{value:06X}")

        choice = input("\nEnter preset name or hex value (0xFFFFFF): ").strip().lower()

        if choice in COLOR_PRESETS:
            self.template["embed"]["color"] = COLOR_PRESETS[choice]
            print(f"✓ Color set to {choice}")
        elif choice.startswith("0x"):
            try:
                color_val = int(choice, 16)
                self.template["embed"]["color"] = color_val
                print(f"✓ Color set to {choice}")
            except ValueError:
                print("✗ Invalid hex value")
        else:
            print("✗ Invalid choice")

    def edit_field(self):
        """Edit an existing field."""
        fields = self.template["embed"].get("fields", [])
        if not fields:
            print("\n✗ No fields to edit")
            return

        self.display_embed(self.template["embed"])

        try:
            idx = int(input("\nEnter field number to edit (1-N): ")) - 1
            if idx < 0 or idx >= len(fields):
                print("✗ Invalid field number")
                return
        except ValueError:
            print("✗ Invalid input")
            return

        field = fields[idx]
        print(f"\nEditing field: {field['name']}")
        print(f"Current value: {field['value'][:100]}...")

        new_name = input("\nNew name (or Enter to keep): ").strip()
        if new_name:
            field["name"] = new_name

        print("\nNew value (Enter on empty line to finish):")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)

        if lines:
            field["value"] = "\n".join(lines)

        inline_choice = input("\nInline? (y/n, or Enter to keep): ").strip().lower()
        if inline_choice == "y":
            field["inline"] = True
        elif inline_choice == "n":
            field["inline"] = False

        print("✓ Field updated")

    def add_field(self):
        """Add a new field."""
        print("\n--- Add New Field ---")

        name = input("Field name: ").strip()
        if not name:
            print("✗ Name required")
            return

        print("Field value (Enter on empty line to finish):")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)

        value = "\n".join(lines) if lines else "-"

        inline_choice = input("Inline? (y/n): ").strip().lower()
        inline = inline_choice == "y"

        field = {"name": name, "value": value, "inline": inline}
        self.template["embed"].setdefault("fields", []).append(field)

        print("✓ Field added")

    def remove_field(self):
        """Remove a field."""
        fields = self.template["embed"].get("fields", [])
        if not fields:
            print("\n✗ No fields to remove")
            return

        self.display_embed(self.template["embed"])

        try:
            idx = int(input("\nEnter field number to remove (1-N): ")) - 1
            if idx < 0 or idx >= len(fields):
                print("✗ Invalid field number")
                return
        except ValueError:
            print("✗ Invalid input")
            return

        removed = fields.pop(idx)
        print(f"✓ Removed field: {removed['name']}")

    def reorder_fields(self):
        """Reorder fields."""
        fields = self.template["embed"].get("fields", [])
        if len(fields) < 2:
            print("\n✗ Need at least 2 fields to reorder")
            return

        self.display_embed(self.template["embed"])

        try:
            from_idx = int(input("\nMove field number: ")) - 1
            to_idx = int(input("To position: ")) - 1

            if from_idx < 0 or from_idx >= len(fields):
                print("✗ Invalid source field")
                return
            if to_idx < 0 or to_idx >= len(fields):
                print("✗ Invalid target position")
                return

            field = fields.pop(from_idx)
            fields.insert(to_idx, field)
            print("✓ Field reordered")
        except (ValueError, IndexError):
            print("✗ Invalid input")

    def save_template(self):
        """Save current template to file."""
        templates_dir = Path(__file__).parent / "alert_templates"
        templates_dir.mkdir(exist_ok=True)

        filename = input("\nTemplate filename (e.g., my_layout.json): ").strip()
        if not filename:
            print("✗ Filename required")
            return

        if not filename.endswith(".json"):
            filename += ".json"

        filepath = templates_dir / filename

        try:
            with open(filepath, "w") as f:
                json.dump(self.template, f, indent=2)
            print(f"✓ Template saved to {filepath}")
        except Exception as e:
            print(f"✗ Error saving template: {e}")

    def test_with_discord(self):
        """Send test embed to Discord webhook."""
        webhook_url = self.settings.discord_webhook_url

        if not webhook_url:
            webhook_url = input("\nDiscord webhook URL: ").strip()
            if not webhook_url:
                print("✗ Webhook URL required")
                return

        print("\n🚀 Sending test embed to Discord...")

        payload = {"embeds": [self.template["embed"]]}

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code in (200, 204):
                print("✓ Test embed sent successfully!")
                print("  Check your Discord channel to verify appearance.")
            else:
                print(f"✗ Discord returned status {response.status_code}")
                print(f"  Response: {response.text}")
        except Exception as e:
            print(f"✗ Error sending to Discord: {e}")

    def main_menu(self):
        """Display main menu and handle user input."""
        while True:
            print("\n" + "=" * 70)
            print("  ALERT LAYOUT PLAYGROUND")
            print("=" * 70)
            print("\n1. View current layout")
            print("2. Edit title")
            print("3. Edit color")
            print("4. Edit field")
            print("5. Add field")
            print("6. Remove field")
            print("7. Reorder fields")
            print("8. Compare before/after")
            print("9. Save template")
            print("10. Test with Discord")
            print("11. Reset to original")
            print("12. Exit")

            choice = input("\nChoice: ").strip()

            if choice == "1":
                self.display_embed(self.template["embed"])
            elif choice == "2":
                self.edit_title()
            elif choice == "3":
                self.edit_color()
            elif choice == "4":
                self.edit_field()
            elif choice == "5":
                self.add_field()
            elif choice == "6":
                self.remove_field()
            elif choice == "7":
                self.reorder_fields()
            elif choice == "8":
                self.compare_embeds()
            elif choice == "9":
                self.save_template()
            elif choice == "10":
                self.test_with_discord()
            elif choice == "11":
                self.template = json.loads(json.dumps(self.original_template))
                print("✓ Reset to original template")
            elif choice == "12":
                print("\n👋 Goodbye!")
                break
            else:
                print("✗ Invalid choice")


def load_template(filepath: str) -> Optional[Dict]:
    """Load a template from file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading template: {e}")
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive alert layout playground",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--load",
        "--template",
        dest="template_file",
        help="Load a saved template file",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Test the template immediately without entering interactive mode",
    )

    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List all available templates and exit",
    )

    args = parser.parse_args()

    # List templates and exit
    if args.list_templates:
        templates_dir = Path(__file__).parent / "alert_templates"
        if not templates_dir.exists():
            print("\n📁 No templates directory found")
            return

        templates = list(templates_dir.glob("*.json"))
        if not templates:
            print("\n📁 No templates found")
            return

        print("\n📋 Available Templates:")
        print("=" * 60)
        for template_path in sorted(templates):
            print(f"\n  {template_path.name}")
            try:
                template = load_template(str(template_path))
                if template:
                    print(f"    Name: {template.get('name', 'N/A')}")
                    print(f"    Description: {template.get('description', 'N/A')}")
            except Exception:
                pass
        print("\n" + "=" * 60)
        return

    # Load template if specified
    template = None
    if args.template_file:
        template = load_template(args.template_file)
        if not template:
            print(f"✗ Failed to load template: {args.template_file}")
            return
        print(f"✓ Loaded template: {template.get('name', 'Unknown')}")

    # Create playground
    playground = EmbedPlayground(template)

    # Test mode: send to Discord and exit
    if args.test:
        playground.display_embed(playground.template["embed"])
        playground.test_with_discord()
        return

    # Interactive mode
    print("\n🎨 Alert Layout Playground")
    print("   Design and test Discord embed layouts interactively")
    playground.main_menu()


if __name__ == "__main__":
    main()
