# Alert Testing System

Professional-grade tools for testing and fine-tuning Discord alert appearance without waiting for real catalysts.

## Overview

This alert testing system provides two complementary tools that allow rapid iteration on alert design:

1. **`test_alert_appearance.py`** - Send customizable dummy alerts to Discord
2. **`alert_layout_playground.py`** - Interactive embed layout editor with live preview

Together, these tools enable you to:
- Test different alert layouts in seconds
- Fine-tune embed appearance before production
- Create reusable layout templates
- Verify webhook configuration
- Test charts, colors, and field arrangements
- Validate negative alert formatting
- Debug rate limiting and error handling

## Quick Start

### 1. Install (No additional dependencies required)

The testing tools use only the existing bot infrastructure - no extra packages needed.

### 2. Configure Webhook

Ensure your `.env` file has a Discord webhook configured:

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### 3. Send Your First Test Alert

```bash
# Use a preset scenario
python scripts/test_alert_appearance.py --preset bullish_fda

# Or create a custom alert
python scripts/test_alert_appearance.py \
  --ticker ABCD \
  --price 3.45 \
  --catalyst "FDA approval" \
  --sentiment 0.85
```

### 4. Design a Custom Layout

```bash
# Start the interactive playground
python scripts/alert_layout_playground.py

# Follow the menu to edit fields, colors, and layout
# Test directly in Discord
# Save as a reusable template
```

## File Structure

```
scripts/
├── test_alert_appearance.py      # Main testing tool
├── alert_layout_playground.py    # Interactive layout editor
├── ALERT_TESTING_GUIDE.md        # Complete documentation
├── ALERT_TESTING_QUICKREF.md     # Quick reference card
├── README_ALERT_TESTING.md       # This file
└── alert_templates/               # Saved layout templates
    ├── minimal_layout.json
    ├── detailed_biotech.json
    ├── negative_warning.json
    └── compact_mobile.json
```

## Use Cases

### Test Alert Appearance

**Scenario:** You want to verify how FDA approval alerts look before going live.

```bash
python scripts/test_alert_appearance.py --preset bullish_fda
```

Check Discord → Looks good? ✓ Ready for production.

### Rapid Layout Iteration

**Scenario:** You need to redesign the price/volume field layout.

```bash
python scripts/alert_layout_playground.py
# Edit fields 1-3
# Test with Discord (menu option 10)
# Iterate until satisfied
# Save template (menu option 9)
```

### Test Negative Alerts

**Scenario:** Verify that offering alerts display with proper warning formatting.

```bash
python scripts/test_alert_appearance.py --preset bearish_offering
```

Check for:
- Red color (0xFF0000)
- Warning emoji in title
- Prominent warning field
- Negative score display

### Batch Testing

**Scenario:** You changed the alert generation code and need to verify all alert types.

```bash
# Test all 9 presets sequentially
for preset in bullish_fda bullish_partnership bullish_clinical neutral_data \
              bearish_offering bearish_warrant energy_discovery tech_contract \
              compliance_regained; do
  echo "Testing: $preset"
  python scripts/test_alert_appearance.py --preset $preset --no-charts
  sleep 2
done
```

### Mobile Layout Testing

**Scenario:** Alerts look great on desktop but cluttered on mobile.

```bash
# Load mobile-optimized template
python scripts/alert_layout_playground.py \
  --template alert_templates/compact_mobile.json \
  --test

# Check on mobile device
# Adjust field count/size as needed
```

## Key Features

### test_alert_appearance.py

✅ **9 Preset Scenarios**
- Bullish: FDA, Partnership, Clinical, Energy, Tech contracts, Compliance
- Neutral: Mixed data
- Bearish: Offerings, Warrants

✅ **Customizable Parameters**
- Ticker, price, volume, sentiment, score
- Catalyst type, reason, LLM analysis
- Negative alert formatting

✅ **Fast Iteration**
- `--no-charts` flag for instant testing
- Custom webhook override
- Direct integration with existing alert infrastructure

✅ **Real Market Simulation**
- Calculates RVol, price changes, volume ratios
- Realistic field values
- Proper timestamp formatting

### alert_layout_playground.py

✅ **Interactive Editing**
- View current layout
- Edit title, color, fields
- Add/remove/reorder fields
- Before/after comparison

✅ **Template Management**
- Save custom layouts as JSON
- Load and edit existing templates
- Export for production use
- Share templates with team

✅ **Live Testing**
- Send test embeds directly to Discord
- Verify appearance in real channel
- Iterate quickly on changes

✅ **Color Presets**
- Named color presets (green, blue, red, etc.)
- Custom hex values
- Visual color codes

## Documentation

### 📖 Full Guide
**`ALERT_TESTING_GUIDE.md`** - Complete documentation including:
- Detailed usage instructions
- All command-line options
- Interactive playground walkthrough
- Advanced usage patterns
- Troubleshooting guide
- Best practices

### 📋 Quick Reference
**`ALERT_TESTING_QUICKREF.md`** - Fast lookup for:
- Common commands
- Preset table
- Template list
- Parameter reference
- Color codes
- Troubleshooting quick fixes

## Example Workflows

### Workflow 1: New Catalyst Type

You're adding support for a new catalyst type (e.g., "merger acquisition").

1. Create test alert with new type:
   ```bash
   python scripts/test_alert_appearance.py \
     --ticker ACQR \
     --title "ACQR Announces Merger with Industry Leader" \
     --catalyst "merger" \
     --sentiment 0.80 \
     --score 8.2 \
     --no-charts
   ```

2. Verify appearance in Discord

3. If layout needs customization:
   ```bash
   python scripts/alert_layout_playground.py
   # Customize fields for merger-specific data
   # Save as alert_templates/merger_layout.json
   ```

4. Test final layout:
   ```bash
   python scripts/alert_layout_playground.py \
     --template alert_templates/merger_layout.json \
     --test
   ```

5. Deploy to production with confidence ✓

### Workflow 2: A/B Testing Layouts

Compare two different alert layouts to see which is clearer.

1. Create Layout A:
   ```bash
   python scripts/alert_layout_playground.py
   # Design layout, save as layout_a.json
   ```

2. Create Layout B:
   ```bash
   python scripts/alert_layout_playground.py
   # Design alternative, save as layout_b.json
   ```

3. Test both in sequence:
   ```bash
   python scripts/alert_layout_playground.py --template alert_templates/layout_a.json --test
   sleep 3
   python scripts/alert_layout_playground.py --template alert_templates/layout_b.json --test
   ```

4. Gather team feedback from Discord channel

5. Deploy winning layout

### Workflow 3: Production Verification

Before deploying a new bot version, verify all alert types work correctly.

1. Test positive catalysts:
   ```bash
   python scripts/test_alert_appearance.py --preset bullish_fda
   python scripts/test_alert_appearance.py --preset bullish_partnership
   python scripts/test_alert_appearance.py --preset energy_discovery
   ```

2. Test negative catalysts:
   ```bash
   python scripts/test_alert_appearance.py --preset bearish_offering
   python scripts/test_alert_appearance.py --preset bearish_warrant
   ```

3. Test edge cases:
   ```bash
   # Very long title
   python scripts/test_alert_appearance.py --title "$(printf 'A%.0s' {1..250})"

   # Extreme price movement
   python scripts/test_alert_appearance.py --price 10.00 --prev-close 2.00

   # Negative score
   python scripts/test_alert_appearance.py --score -8.0 --negative
   ```

4. Verify all display correctly ✓

## Integration with Production

### Using Test Data in Development

The `create_dummy_item()` function can be imported for testing other bot components:

```python
from scripts.test_alert_appearance import create_dummy_item, PRESETS

# Create test data for unit tests
test_item = create_dummy_item(ticker="TEST", price=5.00, sentiment=0.8)

# Use in test suite
def test_alert_formatting():
    item = test_item["item"]
    scored = test_item["scored"]
    # Test your code...
```

### Applying Custom Templates

To use a custom template in production alerts:

1. Design and test template:
   ```bash
   python scripts/alert_layout_playground.py
   # Save as production_layout.json
   ```

2. Load template in `alerts.py`:
   ```python
   import json
   from pathlib import Path

   def load_alert_template(name: str) -> dict:
       template_path = Path("scripts/alert_templates") / f"{name}.json"
       with open(template_path) as f:
           return json.load(f)

   # In build_embed or similar:
   template = load_alert_template("production_layout")
   embed = template["embed"].copy()
   # Populate with real data...
   ```

3. Deploy with confidence knowing layout is tested ✓

## Tips & Tricks

### Speed Up Testing

```bash
# Disable charts for 5-10x faster iteration
alias test-alert='python scripts/test_alert_appearance.py --no-charts'

test-alert --preset bullish_fda
test-alert --ticker MYCO --price 4.50
```

### Create Preset Library

```bash
# Save your most-used configurations as presets
# Edit test_alert_appearance.py and add to PRESETS dict:

PRESETS["my_custom"] = {
    "ticker": "CUST",
    "title": "Custom Alert Type",
    "price": 3.00,
    # ... more params
}

# Use like any other preset
python scripts/test_alert_appearance.py --preset my_custom
```

### Template Versioning

```bash
# Version control your templates
git add scripts/alert_templates/
git commit -m "Add new biotech catalyst layout v2"

# Share with team
git push origin feature/new-alert-layout
```

### Automated Testing

```bash
# Add to CI/CD pipeline
#!/bin/bash
# tests/test_alerts.sh

echo "Testing alert appearance..."

python scripts/test_alert_appearance.py --preset bullish_fda --no-charts || exit 1
python scripts/test_alert_appearance.py --preset bearish_offering --no-charts || exit 1

echo "✓ Alert tests passed"
```

## Troubleshooting

### Common Issues

**Q: Alerts not appearing in Discord?**

A: Verify webhook URL:
```bash
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

**Q: Charts not generating?**

A: Use `--no-charts` to test layout first, then debug charts separately.

**Q: Rate limit errors (429)?**

A: Add `sleep 2` between tests or adjust `ALERTS_MIN_INTERVAL_MS` in `.env`.

**Q: Template won't load?**

A: Validate JSON syntax:
```bash
python -m json.tool scripts/alert_templates/my_layout.json
```

See `ALERT_TESTING_GUIDE.md` for detailed troubleshooting.

## Contributing

### Adding New Presets

1. Edit `test_alert_appearance.py`
2. Add entry to `PRESETS` dict
3. Test thoroughly
4. Document in `ALERT_TESTING_GUIDE.md`

### Adding New Templates

1. Design in playground
2. Save to `alert_templates/`
3. Add description to this README
4. Commit to git

### Improving Documentation

- Keep examples practical and tested
- Update quick reference with common patterns
- Add troubleshooting entries for new issues

## Support

For questions or issues:

1. Check `ALERT_TESTING_GUIDE.md` for detailed help
2. Review `ALERT_TESTING_QUICKREF.md` for quick answers
3. Test with minimal examples first
4. Check bot logs for detailed errors

## License

Part of the Catalyst-Bot project. See main repository LICENSE.

---

**Last Updated:** 2025-10-18
**Version:** 1.0
**Tools:** test_alert_appearance.py, alert_layout_playground.py
**Python:** 3.8+
