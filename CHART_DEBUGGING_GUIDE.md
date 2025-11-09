# Chart Debugging Guide - Enhanced Logging

**Date:** 2025-10-23
**Status:** Comprehensive chart debugging added to track recurring chart embedding issue

---

## 🔍 Problem Statement

**Issue:** Charts are being generated successfully but NOT appearing in Discord alerts. This is a recurring issue that has happened multiple times despite clearing caches.

**What We Know:**
- ✅ Charts ARE being generated (confirmed in logs)
- ✅ Chart files exist on disk with valid file sizes
- ✅ Chart paths are being set correctly in embed references
- ❌ Charts NOT appearing in Discord messages

**Root Cause:** Unknown - likely Discord webhook/API issue with file attachments

---

## 📊 Debugging Enhancements Added

### **1. Chart Generation Phase** (`alerts.py:1022-1046`)

**New Logs:**
```
CHART_DEBUG cache_check ticker=AAPL tf=1D cached_path=... from_cache=True
CHART_DEBUG cache_miss ticker=AAPL tf=1D generating_new_chart=True
CHART_DEBUG generating chart ticker=AAPL tf=1D
CHART_DEBUG chart_generated ticker=AAPL path=... exists=True
CHART_DEBUG chart_file_stats ticker=AAPL size=86859 modified=... absolute_path=...
```

**What to Look For:**
- ❌ `CHART_ERROR chart_generation_returned_none` - Chart generation failed
- ❌ `CHART_ERROR chart_path_does_not_exist` - File wasn't created
- ✅ `size=0` - Empty file (generation bug)
- ✅ `from_cache=True` - Using cached chart (verify cache isn't stale)

---

### **2. Embed Modification Phase** (`alerts.py:1053-1071`)

**New Logs:**
```
CHART_DEBUG attaching_chart_to_embed ticker=AAPL chart_filename=AAPL_1D_20251023-150353.png
EMBED_DEBUG before_modification ticker=AAPL embed_has_image=False embed_has_thumbnail=False
EMBED_DEBUG after_modification ticker=AAPL image_url=attachment://AAPL_1D_20251023-150353.png
EMBED_DEBUG embed_keys=['title', 'url', 'color', 'timestamp', 'fields', 'footer', 'image']
```

**What to Look For:**
- ❌ `embed_has_image=True` BEFORE modification - Something else already set image field
- ❌ `image_url` doesn't start with `attachment://` - Wrong URL format
- ❌ Missing `'image'` in `embed_keys` after modification - Embed modification failed

---

### **3. Pre-Post Phase** (`alerts.py:1100-1118`)

**New Logs:**
```
CHART_DEBUG calling_post_embed_with_attachment ticker=AAPL
CHART_DEBUG pre_post ticker=AAPL chart_path=... chart_exists=True chart_size=86859
CHART_DEBUG pre_post ticker=AAPL embed_image=attachment://... embed_thumbnail=attachment://...
CHART_DEBUG additional_files_count=1 gauge_path=... gauge_exists=True
```

**What to Look For:**
- ❌ `chart_exists=False` - File deleted between generation and upload
- ❌ `chart_size=0` - File became empty
- ❌ `embed_image` doesn't match `chart_filename` - Embed was modified incorrectly

---

### **4. Discord Webhook Upload Phase** (`discord_upload.py:83-148`)

**New Logs:**
```
WEBHOOK_DEBUG file_path=... file_exists=True
WEBHOOK_DEBUG file_size_bytes=86859 file_absolute_path=C:\...\AAPL_1D_20251023-150353.png
WEBHOOK_DEBUG additional_file[0] name=sentiment_gauge.png size=12345
WEBHOOK_DEBUG embed_image_before=attachment://AAPL_1D_20251023-150353.png
WEBHOOK_DEBUG embed_json={...full embed JSON...}
WEBHOOK_DEBUG files_dict_keys=['files[0]', 'files[1]']
WEBHOOK_DEBUG webhook_response status=200 files=2 content_length=1234
WEBHOOK_SUCCESS response_preview={"id": "...", "channel_id": "..."}
```

**What to Look For:**
- ❌ `status=400` - Discord rejected the request
- ❌ `status=429` - Rate limited
- ❌ `files_dict_keys=[]` - No files being uploaded
- ❌ `WEBHOOK_ERROR_DETAIL empty_message_detected` - Embed is malformed
- ❌ `WEBHOOK_ERROR_DETAIL attachment_issue` - Discord specifically reported attachment problem

---

### **5. Discord Bot API Upload Phase** (`discord_upload.py:245-292`)

**New Logs (if using bot token):**
```
BOT_API_DEBUG posting_to_bot_api url=https://discord.com/api/v10/channels/.../messages
BOT_API_DEBUG file_attachment name=... exists=True size=86859
BOT_API_DEBUG components_count count=5
BOT_API_DEBUG attachments_array=[{"id": 0, "filename": "...", "description": "Chart"}]
BOT_API_DEBUG embed_image=attachment://... embed_thumbnail=attachment://...
BOT_API_DEBUG response status=200 files=2 content_length=1234
BOT_API_SUCCESS response_preview={"id": "...", "channel_id": "..."}
```

**What to Look For:**
- ❌ `status=400` with `BOT_API_ERROR_DETAIL invalid_form_body` - Payload structure wrong
- ❌ `BOT_API_ERROR_DETAIL attachment_issue` - Discord bot API rejected attachments

---

### **6. Post-Upload Phase** (`alerts.py:1127-1131`)

**New Logs:**
```
CHART_DEBUG post_embed_result ticker=AAPL success=True
alert_sent_advanced_chart ticker=AAPL tf=1D
```

**OR (on failure):**
```
CHART_DEBUG post_embed_result ticker=AAPL success=False
CHART_ERROR post_embed_failed ticker=AAPL chart_path=... webhook_url_present=True
```

**What to Look For:**
- ❌ `success=False` - Discord upload failed (check webhook logs above)

---

## 🎯 How to Use This Debugging

### **When Charts Are Missing:**

1. **Grep for the ticker in logs:**
   ```bash
   grep "CHART_DEBUG\|WEBHOOK_DEBUG\|BOT_API_DEBUG\|CHART_ERROR" data/logs/bot.jsonl | grep "ticker=AAPL"
   ```

2. **Check the full flow for ONE alert:**
   ```bash
   # Find timestamp of alert
   grep "ticker=AAPL" data/logs/bot.jsonl | tail -1

   # Get all chart-related logs around that time
   grep "2025-10-23T15:03" data/logs/bot.jsonl | grep "CHART_DEBUG\|WEBHOOK"
   ```

3. **Look for these patterns:**

   **Pattern A: Chart generation failed**
   ```
   CHART_DEBUG generating chart ticker=AAPL
   CHART_ERROR chart_generation_returned_none ticker=AAPL
   ```
   → **Root cause:** `generate_multi_panel_chart()` returning None

   **Pattern B: Chart generated but file doesn't exist**
   ```
   CHART_DEBUG chart_generated ticker=AAPL exists=False
   CHART_ERROR chart_path_does_not_exist ticker=AAPL
   ```
   → **Root cause:** File system issue or path problem

   **Pattern C: Chart generated, file exists, but upload failed**
   ```
   CHART_DEBUG chart_file_stats ticker=AAPL size=86859
   CHART_DEBUG calling_post_embed_with_attachment ticker=AAPL
   WEBHOOK_ERROR status=400 response_full={"message": "..."}
   CHART_DEBUG post_embed_result ticker=AAPL success=False
   ```
   → **Root cause:** Discord webhook rejected the request (check error message)

   **Pattern D: Chart uploaded successfully but still not visible**
   ```
   CHART_DEBUG chart_file_stats ticker=AAPL size=86859
   WEBHOOK_SUCCESS response_preview={"id": "..."}
   CHART_DEBUG post_embed_result ticker=AAPL success=True
   ```
   → **Root cause:** Discord API accepted but didn't render (Discord bug?)

---

## 🔧 Troubleshooting Steps

### **If Pattern A (Generation Failed):**
1. Check if `charts_advanced.py` is throwing exceptions
2. Verify matplotlib/mplfinance installed
3. Check disk space
4. Look for errors in chart generation code

### **If Pattern B (File Missing):**
1. Check `out/charts/` directory exists
2. Verify file permissions
3. Check antivirus/security software (might be deleting PNGs)
4. Look for race conditions (file deleted before upload)

### **If Pattern C (Upload Failed):**
1. **Check Discord error message** in `WEBHOOK_ERROR response_full=...`
2. Common errors:
   - `"Cannot send an empty message"` → Embed is malformed
   - `"Invalid Form Body"` → JSON structure wrong
   - `"attachments"` error → File upload format wrong
   - `429 Too Many Requests` → Rate limited

3. **Verify webhook URL:**
   ```bash
   echo $DISCORD_WEBHOOK_URL
   # Should be: https://discord.com/api/webhooks/{id}/{token}
   ```

4. **Test webhook manually:**
   ```bash
   curl -X POST $DISCORD_WEBHOOK_URL \
     -H "Content-Type: application/json" \
     -d '{"content": "Test message"}'
   ```

### **If Pattern D (Accepted But Not Visible):**
1. **This is the CRITICAL case** - Discord accepted the request but didn't show the chart
2. Check Discord response JSON:
   ```
   WEBHOOK_SUCCESS response_preview={"id": "123", "channel_id": "456", "embeds": [...]}
   ```
3. Check if `embeds` array in response includes `image` field
4. Manually check Discord message via API:
   ```bash
   curl https://discord.com/api/v10/channels/{channel_id}/messages/{message_id} \
     -H "Authorization: Bot {bot_token}"
   ```
5. If Discord API shows image in response but NOT visible:
   → **Discord client bug or attachment serving issue**

---

## 📝 Expected Log Flow (Success Case)

```
CHART_DEBUG cache_miss ticker=AAPL tf=1D generating_new_chart=True
CHART_DEBUG generating chart ticker=AAPL tf=1D
generating_advanced_chart ticker=AAPL tf=1D
CHART_DEBUG chart_generated ticker=AAPL path=out\charts\AAPL_1D_20251023-150353.png exists=True
CHART_DEBUG chart_file_stats ticker=AAPL size=86859 modified=1729697033.123 absolute_path=C:\...\out\charts\AAPL_1D_20251023-150353.png

CHART_DEBUG attaching_chart_to_embed ticker=AAPL chart_filename=AAPL_1D_20251023-150353.png
EMBED_DEBUG before_modification ticker=AAPL embed_has_image=False embed_has_thumbnail=False
EMBED_DEBUG after_modification ticker=AAPL image_url=attachment://AAPL_1D_20251023-150353.png
EMBED_DEBUG embed_keys=['title', 'url', 'color', 'timestamp', 'fields', 'footer', 'image']

CHART_DEBUG calling_post_embed_with_attachment ticker=AAPL
CHART_DEBUG pre_post ticker=AAPL chart_path=out\charts\AAPL_1D_20251023-150353.png chart_exists=True chart_size=86859
CHART_DEBUG pre_post ticker=AAPL embed_image=attachment://AAPL_1D_20251023-150353.png embed_thumbnail=None

WEBHOOK_DEBUG file_path=out\charts\AAPL_1D_20251023-150353.png file_exists=True
WEBHOOK_DEBUG file_size_bytes=86859 file_absolute_path=C:\...\out\charts\AAPL_1D_20251023-150353.png
WEBHOOK_DEBUG embed_image_before=attachment://AAPL_1D_20251023-150353.png
WEBHOOK_DEBUG embed_json={"title": "...", "image": {"url": "attachment://AAPL_1D_20251023-150353.png"}, ...}
WEBHOOK_DEBUG files_dict_keys=['files[0]']
WEBHOOK_DEBUG uploading chart as files[0] filename=AAPL_1D_20251023-150353.png
WEBHOOK_DEBUG webhook_response status=200 files=1 content_length=1234
WEBHOOK_SUCCESS response_preview={"id": "1234567890", "channel_id": "..."}

CHART_DEBUG post_embed_result ticker=AAPL success=True
alert_sent_advanced_chart ticker=AAPL tf=1D
```

---

## 🚨 Next Steps When Issue Occurs

1. **Immediately capture full log context:**
   ```bash
   # Save last 1000 lines when chart is missing
   tail -1000 data/logs/bot.jsonl > chart_issue_$(date +%Y%m%d_%H%M%S).log
   ```

2. **Identify which pattern matches** (A, B, C, or D above)

3. **If Pattern D (Discord accepted but not visible):**
   - This is the most mysterious case
   - Check if Discord is having API issues: https://discordstatus.com/
   - Try posting to a different channel/webhook
   - Try using bot API instead of webhook (or vice versa)

4. **Create minimal reproduction:**
   ```python
   # Test script: test_chart_upload.py
   import requests
   from pathlib import Path

   webhook_url = "https://discord.com/api/webhooks/..."
   chart_path = Path("out/charts/AAPL_1D_20251023-150353.png")

   with open(chart_path, "rb") as f:
       files = {"files[0]": (chart_path.name, f, "image/png")}
       payload = {
           "payload_json": json.dumps({
               "embeds": [{
                   "title": "Test Chart",
                   "image": {"url": f"attachment://{chart_path.name}"}
               }]
           })
       }
       r = requests.post(webhook_url, data=payload, files=files)
       print(f"Status: {r.status_code}")
       print(f"Response: {r.text}")
   ```

---

## 📊 Monitoring Commands

**Real-time chart debugging:**
```bash
# Watch chart-related logs in real-time
tail -f data/logs/bot.jsonl | grep --line-buffered "CHART_DEBUG\|WEBHOOK_DEBUG\|CHART_ERROR"
```

**Count chart successes vs failures:**
```bash
grep "CHART_DEBUG post_embed_result" data/logs/bot.jsonl | \
  awk '{print $NF}' | sort | uniq -c
# Expected output:
#   123 success=True
#     5 success=False
```

**Find all charts that failed to upload:**
```bash
grep "CHART_ERROR post_embed_failed" data/logs/bot.jsonl | \
  awk -F'ticker=' '{print $2}' | awk '{print $1}' | sort | uniq
```

**Check Discord webhook health:**
```bash
grep "WEBHOOK_ERROR\|WEBHOOK_SUCCESS" data/logs/bot.jsonl | tail -20
```

---

## 📞 Quick Reference

### **Files Modified:**
- `src/catalyst_bot/alerts.py` - Chart generation and embed modification debugging
- `src/catalyst_bot/discord_upload.py` - Webhook/bot API upload debugging

### **New Log Prefixes:**
- `CHART_DEBUG` - Chart generation and file handling
- `CHART_ERROR` - Chart-related errors
- `EMBED_DEBUG` - Embed modification tracking
- `WEBHOOK_DEBUG` - Webhook upload details
- `WEBHOOK_ERROR` - Webhook failures
- `WEBHOOK_SUCCESS` - Webhook successful uploads
- `BOT_API_DEBUG` - Bot API upload details
- `BOT_API_ERROR` - Bot API failures
- `BOT_API_SUCCESS` - Bot API successful uploads

### **Critical Metrics to Track:**
1. **Chart generation success rate** - Should be ~100%
2. **Chart file existence rate** - Should be ~100%
3. **Webhook upload success rate** - Should be >95%
4. **Webhook accepts but chart not visible rate** - **This is the key metric**

If #4 is >0%, we have a Discord-side issue or a subtle attachment format problem.

---

**Created:** 2025-10-23
**Updated:** 2025-10-23
**Status:** Active Debugging Enhanced
