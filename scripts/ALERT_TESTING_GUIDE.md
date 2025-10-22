# Alert Testing Guide

Complete guide for testing and fine-tuning Discord alert appearance without waiting for real catalysts.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Test Alert Appearance Tool](#test-alert-appearance-tool)
4. [Alert Layout Playground](#alert-layout-playground)
5. [Available Presets](#available-presets)
6. [Advanced Usage](#advanced-usage)
7. [Troubleshooting](#troubleshooting)

---

## Overview

The alert testing system provides two complementary tools:

### 1. **test_alert_appearance.py** - Send Test Alerts
- Quickly send dummy alerts with customizable parameters
- Use preset scenarios or create custom test cases
- Test different catalyst types, sentiment scores, and metrics
- Verify chart generation, RVol calculations, and LLM analysis display

### 2. **alert_layout_playground.py** - Design Alert Layouts
- Interactive CLI for editing embed structure
- Live preview of changes
- Before/after comparison
- Save custom layouts as reusable templates
- Test layouts with real Discord webhooks

---

## Quick Start

### Prerequisites

```bash
# Ensure .env is configured with Discord webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### Basic Test Alert

```bash
# Send a default test alert
python scripts/test_alert_appearance.py

# Use a preset scenario
python scripts/test_alert_appearance.py --preset bullish_fda

# List all available presets
python scripts/test_alert_appearance.py --list-presets
```

### Basic Layout Editing

```bash
# Start interactive playground
python scripts/alert_layout_playground.py

# Load a saved template
python scripts/alert_layout_playground.py --load templates/my_layout.json

# Test a template without interaction
python scripts/alert_layout_playground.py --template templates/my_layout.json --test
```

---

## Test Alert Appearance Tool

### Command-Line Options

```bash
python scripts/test_alert_appearance.py [OPTIONS]

Options:
  --preset PRESET         Use a preset scenario (see Available Presets)
  --ticker TICKER         Stock ticker symbol (default: TEST)
  --title TITLE           Alert headline/title
  --price PRICE           Current price (default: 2.50)
  --prev-close PRICE      Previous close price (default: 2.00)
  --volume VOLUME         Current volume (default: 1000000)
  --avg-volume VOLUME     Average volume (default: 500000)
  --catalyst TYPE         Catalyst type (fda, partnership, clinical, etc.)
  --sentiment SCORE       Sentiment score -1.0 to 1.0 (default: 0.5)
  --score SCORE           Catalyst score 0-10 (default: 6.0)
  --reason TEXT           Analysis reason text
  --negative              Make this a negative alert (offering, dilution)
  --llm-analysis TEXT     Custom LLM analysis text
  --no-charts             Disable chart generation for faster iteration
  --webhook URL           Override Discord webhook URL
  --list-presets          List all available preset scenarios
```

### Examples

#### Test FDA Approval Alert
```bash
python scripts/test_alert_appearance.py \
  --ticker ABCD \
  --price 3.45 \
  --prev-close 2.10 \
  --volume 8500000 \
  --catalyst "FDA approval" \
  --sentiment 0.85 \
  --score 8.5 \
  --reason "FDA breakthrough designation - strong catalyst"
```

#### Test Negative Alert (Offering)
```bash
python scripts/test_alert_appearance.py \
  --ticker DILU \
  --price 1.20 \
  --prev-close 1.85 \
  --catalyst "offering" \
  --sentiment -0.75 \
  --score -6.5 \
  --negative
```

#### Quick Iteration Without Charts
```bash
# Test multiple layouts quickly
python scripts/test_alert_appearance.py --preset bullish_fda --no-charts
python scripts/test_alert_appearance.py --preset bearish_offering --no-charts
python scripts/test_alert_appearance.py --preset energy_discovery --no-charts
```

#### Custom Webhook Testing
```bash
# Test with a different Discord channel
python scripts/test_alert_appearance.py \
  --preset bullish_partnership \
  --webhook https://discord.com/api/webhooks/TEST_CHANNEL_ID/TOKEN
```

---

## Alert Layout Playground

### Interactive Menu

When you run the playground, you'll see this menu:

```
==================================================================
  ALERT LAYOUT PLAYGROUND
==================================================================

1. View current layout
2. Edit title
3. Edit color
4. Edit field
5. Add field
6. Remove field
7. Reorder fields
8. Compare before/after
9. Save template
10. Test with Discord
11. Reset to original
12. Exit
```

### Workflow Example

#### 1. Start the Playground
```bash
python scripts/alert_layout_playground.py
```

#### 2. View Current Layout
```
Choice: 1

======================================================================
  Current Layout
======================================================================

Title: [TICKER] Catalyst Headline Goes Here
URL: https://example.com
Color: 0x00FF00

Fields (6):

  1. 💰 Price Action [inline]
     $2.50 (↑ +25.00%)
     Prev: $2.00

  2. 📊 Volume [inline]
     1.5M (RVol: 5.0x)
     Avg: 300K

  [... more fields ...]
```

#### 3. Edit a Field
```
Choice: 4
Enter field number to edit (1-N): 1

Editing field: 💰 Price Action
Current value: $2.50 (↑ +25.00%)...

New name (or Enter to keep): 💵 Price & Change
New value (Enter on empty line to finish):
$2.50 → $2.00 (+25.00%)
Volume: 1.5M

Inline? (y/n, or Enter to keep): y
✓ Field updated
```

#### 4. Add a New Field
```
Choice: 5

--- Add New Field ---
Field name: 🎯 Target Price
Field value (Enter on empty line to finish):
Analyst Target: $5.00
Implied Return: +100%

Inline? (y/n): y
✓ Field added
```

#### 5. Change Color
```
Choice: 3

Current color: 0x00FF00

Presets:
  green: 0x00FF00
  blue: 0x0099FF
  red: 0xFF0000
  orange: 0xFF9900
  purple: 0x9900FF
  yellow: 0xFFFF00
  gray: 0x808080

Enter preset name or hex value (0xFFFFFF): blue
✓ Color set to blue
```

#### 6. Compare Before/After
```
Choice: 8

============================================================================
  BEFORE/AFTER COMPARISON
============================================================================

ORIGINAL                                                    | CURRENT
----------------------------------------------------------------------------
[TICKER] Catalyst Headline Goes Here                        | [TICKER] Catalyst Headline Goes Here
----------------------------------------------------------------------------
💰 Price Action              $2.50 (↑ +25.00%)...           | 💵 Price & Change            $2.50 → $2.00 (+25.00%)...  *
📊 Volume                    1.5M (RVol: 5.0x)...           | 📊 Volume                    1.5M (RVol: 5.0x)...
📈 Score                     8.5/10...                       | 📈 Score                     8.5/10...
---                          ---                             | 🎯 Target Price              Analyst Target: $5.00...      *
============================================================================
* = Changed
```

#### 7. Test with Discord
```
Choice: 10

🚀 Sending test embed to Discord...
✓ Test embed sent successfully!
  Check your Discord channel to verify appearance.
```

#### 8. Save Template
```
Choice: 9

Template filename (e.g., my_layout.json): enhanced_price_display.json
✓ Template saved to scripts/alert_templates/enhanced_price_display.json
```

### Template Management

Templates are saved in `scripts/alert_templates/` and can be reused:

```bash
# List all saved templates
python scripts/alert_layout_playground.py --list-templates

# Load and edit a template
python scripts/alert_layout_playground.py --load alert_templates/enhanced_price_display.json

# Test a template immediately
python scripts/alert_layout_playground.py --template alert_templates/enhanced_price_display.json --test
```

---

## Available Presets

### Bullish Catalysts

#### `bullish_fda`
- **Ticker:** ABCD
- **Type:** FDA breakthrough therapy designation
- **Sentiment:** 0.85 (Very Bullish)
- **Score:** 8.5/10
- **Use Case:** Test high-conviction biotech catalyst alerts

#### `bullish_partnership`
- **Ticker:** WXYZ
- **Type:** Strategic partnership with major pharma
- **Sentiment:** 0.72 (Bullish)
- **Score:** 7.8/10
- **Use Case:** Test partnership/collaboration alerts

#### `bullish_clinical`
- **Ticker:** EFGH
- **Type:** Phase 3 trial success
- **Sentiment:** 0.90 (Very Bullish)
- **Score:** 9.2/10
- **Use Case:** Test strongest catalyst type with statistical significance

#### `energy_discovery`
- **Ticker:** OILX
- **Type:** Major oil discovery
- **Sentiment:** 0.88 (Very Bullish)
- **Score:** 9.0/10
- **Use Case:** Test energy sector catalysts (274.6% avg return per MOA)

#### `tech_contract`
- **Ticker:** GOVX
- **Type:** Federal government contract
- **Sentiment:** 0.78 (Bullish)
- **Score:** 8.3/10
- **Use Case:** Test government contract alerts (54.9% avg return per MOA)

#### `compliance_regained`
- **Ticker:** CMPL
- **Type:** Nasdaq compliance regained
- **Sentiment:** 0.55 (Moderately Bullish)
- **Score:** 6.2/10
- **Use Case:** Test compliance/delisting risk removal alerts

### Neutral/Mixed Catalysts

#### `neutral_data`
- **Ticker:** MNOP
- **Type:** Business update with mixed metrics
- **Sentiment:** 0.15 (Neutral)
- **Score:** 4.2/10
- **Use Case:** Test low-conviction or routine update alerts

### Negative Catalysts (Exit Signals)

#### `bearish_offering`
- **Ticker:** DILU
- **Type:** Dilutive registered direct offering
- **Sentiment:** -0.75 (Very Bearish)
- **Score:** -6.5/10
- **Use Case:** Test negative alert formatting (red color, warning emojis)

#### `bearish_warrant`
- **Ticker:** WRNT
- **Type:** Pre-funded warrant exercise
- **Sentiment:** -0.60 (Bearish)
- **Score:** -5.8/10
- **Use Case:** Test dilution alert formatting

---

## Advanced Usage

### Testing Alert Rate Limiting

Send multiple alerts quickly to test rate limiting:

```bash
# Send 5 alerts with 500ms spacing
for i in {1..5}; do
  python scripts/test_alert_appearance.py --preset bullish_fda --no-charts
  sleep 0.5
done
```

### Testing Different Chart Backends

```bash
# Test QuickChart integration
FEATURE_QUICKCHART=1 python scripts/test_alert_appearance.py --ticker AAPL

# Test local mplfinance charts
FEATURE_RICH_ALERTS=1 FEATURE_QUICKCHART=0 python scripts/test_alert_appearance.py --ticker AAPL

# Test Finviz static charts
FEATURE_FINVIZ_CHART=1 FEATURE_QUICKCHART=0 FEATURE_RICH_ALERTS=0 \
  python scripts/test_alert_appearance.py --ticker AAPL
```

### Testing Market Regime Multipliers

```bash
# Test with different VIX levels (via environment override)
REGIME_MULTIPLIER_BULL=1.3 python scripts/test_alert_appearance.py --preset bullish_fda
REGIME_MULTIPLIER_BEAR=0.6 python scripts/test_alert_appearance.py --preset bullish_fda
```

### Creating Template Collections

Organize templates by use case:

```bash
scripts/alert_templates/
├── biotech_fda.json              # Biotech FDA alerts
├── biotech_clinical.json         # Clinical trial alerts
├── energy_discovery.json         # Energy discovery alerts
├── tech_contracts.json           # Government contract alerts
├── negative_offering.json        # Negative catalyst templates
└── minimal_layout.json           # Minimal field layout
```

### Batch Testing Multiple Presets

Test all presets sequentially:

```bash
# Create a test script
cat > test_all_presets.sh << 'EOF'
#!/bin/bash
for preset in bullish_fda bullish_partnership bullish_clinical neutral_data \
              bearish_offering bearish_warrant energy_discovery tech_contract; do
  echo "Testing preset: $preset"
  python scripts/test_alert_appearance.py --preset $preset --no-charts
  sleep 2
done
EOF

chmod +x test_all_presets.sh
./test_all_presets.sh
```

### Testing Embed Size Limits

Discord embeds have size limits:
- Total embed: 6,000 characters
- Title: 256 characters
- Description: 4,096 characters
- Field name: 256 characters
- Field value: 1,024 characters
- Footer: 2,048 characters
- Max fields: 25

Test edge cases:

```bash
# Long title
python scripts/test_alert_appearance.py \
  --title "$(printf 'A%.0s' {1..300})" \
  --no-charts

# Many fields (create template with 25 fields and test)
python scripts/alert_layout_playground.py
# Add 25 fields, save, and test
```

---

## Troubleshooting

### Alert Not Appearing in Discord

**Problem:** Script reports success but no alert in Discord

**Solutions:**
1. Verify webhook URL:
   ```bash
   curl -X POST "$DISCORD_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"content": "Test message"}'
   ```

2. Check Discord channel permissions
3. Verify webhook is for correct channel
4. Check for rate limiting (429 errors in logs)

### Charts Not Generating

**Problem:** Charts don't appear in test alerts

**Solutions:**
1. Check feature flags in `.env`:
   ```bash
   FEATURE_RICH_ALERTS=1
   # OR
   FEATURE_QUICKCHART=1
   ```

2. Verify chart dependencies:
   ```bash
   pip install matplotlib mplfinance pandas
   ```

3. Test chart generation separately:
   ```bash
   python -c "from src.catalyst_bot.charts import CHARTS_OK; print(CHARTS_OK)"
   ```

4. Use `--no-charts` flag to test alert structure first

### RVol Calculation Issues

**Problem:** RVol shows as 1.0x or "n/a"

**Solution:** RVol requires real market data. For testing, provide custom values:
```bash
python scripts/test_alert_appearance.py \
  --volume 5000000 \
  --avg-volume 800000
  # This will calculate RVol as 6.25x
```

### Template Loading Errors

**Problem:** "Error loading template" message

**Solutions:**
1. Check JSON syntax:
   ```bash
   python -m json.tool templates/my_layout.json
   ```

2. Verify file path:
   ```bash
   ls -la scripts/alert_templates/
   ```

3. Check template structure matches expected format

### Color Not Changing

**Problem:** Embed color stays the same

**Solution:** Discord caches embeds. To see changes:
1. Change the title slightly (add a space)
2. Wait 30-60 seconds
3. Test in a different channel
4. Clear Discord cache (Ctrl+Shift+R)

### Rate Limiting (429 Errors)

**Problem:** "Rate limited by Discord" errors

**Solutions:**
1. Use `--no-charts` to reduce payload size
2. Add delays between tests:
   ```bash
   sleep 2  # Wait 2 seconds between alerts
   ```

3. Adjust rate limit settings in `.env`:
   ```bash
   ALERTS_MIN_INTERVAL_MS=1000  # 1 second minimum spacing
   ```

4. Check `_RL_DEBUG=1` for detailed rate limit info:
   ```bash
   ALERTS_RL_DEBUG=1 python scripts/test_alert_appearance.py
   ```

---

## Best Practices

### 1. Start Simple
- Begin with `--no-charts` for fast iteration
- Use presets to understand expected output
- Test basic layout before adding complexity

### 2. Iterative Design
- Make one change at a time
- Test immediately after each change
- Use before/after comparison to verify changes
- Save working templates before major changes

### 3. Template Organization
- Use descriptive template names
- Add metadata (name, description) to templates
- Create templates for each catalyst type
- Version control templates with git

### 4. Testing Checklist
- [ ] Test with charts enabled/disabled
- [ ] Test positive and negative alerts
- [ ] Test with different sentiment ranges
- [ ] Test field ordering and inline layout
- [ ] Test color themes
- [ ] Verify on mobile Discord app
- [ ] Test with long text (truncation handling)
- [ ] Verify emoji rendering
- [ ] Test rate limiting with rapid alerts

### 5. Production Integration
- Test templates with real webhook before deployment
- Document custom templates in team wiki
- Create preset for each common catalyst type
- Monitor Discord feedback on layout changes
- A/B test layouts if possible (different channels)

---

## Integration with Production

### Using Custom Templates in Production

1. **Export template from playground:**
   ```bash
   python scripts/alert_layout_playground.py
   # Design layout, then: Choice 9 (Save template)
   ```

2. **Modify alerts.py to use template:**
   ```python
   # In src/catalyst_bot/alerts.py
   def load_custom_template(template_name: str) -> Dict:
       template_path = Path("scripts/alert_templates") / f"{template_name}.json"
       with open(template_path) as f:
           return json.load(f)

   # Use in send_alert_safe or build_embed
   custom_embed = load_custom_template("enhanced_price_display")
   # Apply to alert...
   ```

3. **Test before deploying:**
   ```bash
   python scripts/test_alert_appearance.py --preset bullish_fda
   # Verify production webhooks receive correctly
   ```

---

## Support

For issues or questions:
1. Check this guide's [Troubleshooting](#troubleshooting) section
2. Review Discord webhook documentation
3. Test with minimal example first
4. Check bot logs for detailed error messages

---

**Last Updated:** 2025-10-18
**Version:** 1.0
**Tools:** test_alert_appearance.py, alert_layout_playground.py
