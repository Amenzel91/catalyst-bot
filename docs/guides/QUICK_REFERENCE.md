# 📌 Catalyst-Bot Quick Reference

---

## 🚨 Alert Channel Commands

```
/check <ticker>           - Quick price & recent alerts
/research <ticker> [?]    - LLM deep dive analysis
/ask <question>           - Natural language queries
/compare <t1> <t2>        - Side-by-side comparison
```

**Examples:**
```
/check AAPL
/research TSLA "What are the catalysts?"
/ask "Is tech sector bullish?"
/compare NVDA AMD
```

---

## 🛠️ Admin Channel Commands

```
/admin report [date]        - Generate performance report
/admin set <param> <value>  - Update bot parameter
/admin rollback             - Revert to previous config
/admin stats                - Show current parameters
```

**Examples:**
```
/admin report 2025-10-04
/admin set MIN_SCORE 0.30
/admin rollback
```

---

## 📊 Alert Features

**Price Range:** $0.10 - $10.00
**Exchanges:** NASDAQ, NYSE, AMEX
**Deduplication:** Active
**Heartbeat:** Every 60 min

**Chart Buttons:** 1D | 5D | 1M | 3M | 1Y

---

## 🎯 Monitored Catalysts

✅ SEC Filings (8-K, S-1, 10-Q)
✅ Earnings beats/misses
✅ FDA approvals
✅ M&A activity
✅ Contract awards
✅ 52-week lows
✅ Breakout scans
✅ Unusual options

---

## 🕐 Automated Reports

**Daily:** 8:00 PM ET (Admin Report)
**Weekly:** Sunday 8:00 PM ET (Performance Report)

---

## ⚡ Quick Health Check

**Interaction Server:** http://localhost:8081/health
**LLM Status:** http://localhost:11434/api/tags
**Cloudflare:** Check process in Task Manager

---

**Disclaimer:** Informational only. Not financial advice. DYOR.
