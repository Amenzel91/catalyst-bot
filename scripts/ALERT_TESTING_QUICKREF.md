# Alert Testing Quick Reference

Fast reference for common alert testing commands.

## Quick Commands

### Test Presets (Fastest)
```bash
# FDA approval alert
python scripts/test_alert_appearance.py --preset bullish_fda

# Negative alert (offering)
python scripts/test_alert_appearance.py --preset bearish_offering

# Energy discovery
python scripts/test_alert_appearance.py --preset energy_discovery

# List all presets
python scripts/test_alert_appearance.py --list-presets
```

### Fast Iteration (No Charts)
```bash
# Quick test without waiting for charts
python scripts/test_alert_appearance.py --preset bullish_fda --no-charts
```

### Custom Test Alerts
```bash
# Basic custom alert
python scripts/test_alert_appearance.py \
  --ticker ABCD \
  --price 3.45 \
  --prev-close 2.10 \
  --catalyst "FDA approval"

# Negative alert
python scripts/test_alert_appearance.py \
  --ticker DILU \
  --price 1.20 \
  --negative
```

### Layout Editing
```bash
# Start interactive playground
python scripts/alert_layout_playground.py

# Load template
python scripts/alert_layout_playground.py --load alert_templates/minimal_layout.json

# Quick test a template
python scripts/alert_layout_playground.py --template alert_templates/minimal_layout.json --test
```

## Available Presets

| Preset | Type | Sentiment | Score | Use Case |
|--------|------|-----------|-------|----------|
| `bullish_fda` | FDA approval | 0.85 | 8.5 | High-conviction biotech |
| `bullish_partnership` | Partnership | 0.72 | 7.8 | Strategic deals |
| `bullish_clinical` | Phase 3 success | 0.90 | 9.2 | Strongest catalyst |
| `energy_discovery` | Oil/gas find | 0.88 | 9.0 | Energy sector |
| `tech_contract` | Gov contract | 0.78 | 8.3 | Tech contracts |
| `compliance_regained` | Nasdaq compliance | 0.55 | 6.2 | Compliance wins |
| `neutral_data` | Mixed update | 0.15 | 4.2 | Low conviction |
| `bearish_offering` | Dilution | -0.75 | -6.5 | Negative alert |
| `bearish_warrant` | Warrants | -0.60 | -5.8 | Dilution warning |

## Available Templates

| Template | Description | Use Case |
|----------|-------------|----------|
| `minimal_layout.json` | Compact, essential fields | Fast scanning |
| `detailed_biotech.json` | Comprehensive biotech layout | Clinical catalysts |
| `negative_warning.json` | High-visibility warning | Exit signals |
| `compact_mobile.json` | Mobile-optimized | Mobile devices |

## Common Parameters

### Price & Volume
```bash
--price 2.50              # Current price
--prev-close 2.00         # Previous close
--volume 1500000          # Current volume
--avg-volume 300000       # Average volume
```

### Scoring
```bash
--sentiment 0.85          # -1.0 to 1.0
--score 8.5               # 0 to 10
--catalyst "FDA approval" # Catalyst type
```

### Features
```bash
--no-charts              # Disable charts (faster)
--negative               # Negative alert format
--webhook URL            # Custom webhook
```

## Playground Menu

```
1. View current layout     - See full embed structure
2. Edit title             - Change embed title
3. Edit color             - Change color (presets or hex)
4. Edit field             - Modify existing field
5. Add field              - Add new field
6. Remove field           - Delete field
7. Reorder fields         - Change field order
8. Compare before/after   - Side-by-side comparison
9. Save template          - Export as JSON
10. Test with Discord     - Send to webhook
11. Reset to original     - Undo all changes
12. Exit                  - Quit playground
```

## Color Codes

| Color | Hex | Use Case |
|-------|-----|----------|
| Green | `0x00FF00` | Bullish alerts |
| Blue | `0x0099FF` | Neutral/info |
| Red | `0xFF0000` | Negative alerts |
| Orange | `0xFF9900` | Warnings |
| Purple | `0x9900FF` | Special events |
| Yellow | `0xFFFF00` | Attention needed |
| Gray | `0x808080` | Low priority |

## Troubleshooting

### Alert not showing?
```bash
# Test webhook directly
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test"}'
```

### Charts not generating?
```bash
# Check feature flags
echo $FEATURE_RICH_ALERTS
echo $FEATURE_QUICKCHART

# Test without charts
python scripts/test_alert_appearance.py --preset bullish_fda --no-charts
```

### Rate limited?
```bash
# Add delays between tests
python scripts/test_alert_appearance.py --preset bullish_fda
sleep 2
python scripts/test_alert_appearance.py --preset bearish_offering
```

## Batch Testing

### Test all presets
```bash
for preset in bullish_fda bullish_partnership energy_discovery tech_contract; do
  echo "Testing: $preset"
  python scripts/test_alert_appearance.py --preset $preset --no-charts
  sleep 2
done
```

### Test all templates
```bash
python scripts/alert_layout_playground.py --list-templates

for template in alert_templates/*.json; do
  echo "Testing: $template"
  python scripts/alert_layout_playground.py --template "$template" --test
  sleep 2
done
```

## Environment Overrides

### Test different features
```bash
# QuickChart enabled
FEATURE_QUICKCHART=1 python scripts/test_alert_appearance.py --ticker AAPL

# Local charts
FEATURE_RICH_ALERTS=1 FEATURE_QUICKCHART=0 python scripts/test_alert_appearance.py --ticker AAPL

# Finviz fallback
FEATURE_FINVIZ_CHART=1 FEATURE_QUICKCHART=0 FEATURE_RICH_ALERTS=0 \
  python scripts/test_alert_appearance.py --ticker AAPL
```

### Test rate limiting
```bash
# Enable debug logging
ALERTS_RL_DEBUG=1 python scripts/test_alert_appearance.py --preset bullish_fda

# Adjust minimum interval
ALERTS_MIN_INTERVAL_MS=2000 python scripts/test_alert_appearance.py --preset bullish_fda
```

## Integration Examples

### Use in Python
```python
from scripts.test_alert_appearance import create_dummy_item, PRESETS

# Get preset parameters
params = PRESETS["bullish_fda"]

# Create custom test item
item = create_dummy_item(
    ticker="MYCO",
    title="Custom Test Alert",
    price=5.00,
    sentiment=0.8,
)

# Access dummy data
print(item["item"]["ticker"])  # MYCO
print(item["scored"]["score"])  # Score value
```

### Script Integration
```bash
#!/bin/bash
# test_alert_flow.sh

echo "Testing alert appearance system..."

# Test positive catalyst
python scripts/test_alert_appearance.py --preset bullish_fda --no-charts
sleep 2

# Test negative catalyst
python scripts/test_alert_appearance.py --preset bearish_offering --no-charts
sleep 2

# Test custom layout
python scripts/alert_layout_playground.py \
  --template alert_templates/minimal_layout.json --test

echo "Alert testing complete!"
```

---

**Need more help?** See `ALERT_TESTING_GUIDE.md` for detailed documentation.
