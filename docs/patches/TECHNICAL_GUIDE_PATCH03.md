## Catalyst‑Bot Technical Guide — Patch 03

This document describes the deduplication and duplicate suppression changes
introduced in **Patch 03**.  These updates build on the features of
Patch 02 by ensuring that the bot does not repeatedly alert on the same
headline across cycles or restarts.

### Persistent deduplication

Patch 03 enables cross‑cycle deduplication via two complementary mechanisms:

* **Refined dedup index** — When `FEATURE_DEDUP_REFINED=1`, the bot
  persists a *first‑seen* index in `data/dedup/first_seen.db`.  Each
  headline is hashed into a signature (based on canonicalised link and
  normalised title) and stored with a timestamp.  On subsequent cycles,
  signatures that already exist in the index are filtered out.  This
  prevents duplicate alerts even if the feed source republishes an
  identical headline.【816982838989232†screenshot】

* **Seen store** — In addition to the signature index, the bot now
  checks a persistent *seen store* for item IDs before sending an
  alert.  The seen store is implemented in `seen_store.py` and backed
  by `data/seen_ids.sqlite`.  Each item’s stable ID (based on
  link/guid and source) is recorded when the alert is sent.  On the next
  run, any item whose ID has already been seen within the configured TTL
  (`SEEN_TTL_DAYS`) is skipped.  This provides an extra layer of
  protection against duplicate notifications across restarts.

The runner integrates these mechanisms by calling
`seen_store.should_filter(item_id)` early in the alert pipeline.  If
the helper returns `True`, the event is counted as `skipped_seen` and
is not classified or sent.

### Duplicate suppression TTLs

The bot maintains two TTLs to control how long entries remain in the
duplicate caches:

* `SEEN_TTL_SECONDS` — Configures the in‑memory cache used by
  `send_alert_safe` to suppress duplicate alerts within a single process.
  The default is 900 seconds (15 minutes).  Increase this value if you
  run the bot continuously and want to avoid re‑alerting on the same
  headline multiple times per day.  Setting it to `86400` (24 hours) is
  a common choice.

* `SEEN_TTL_DAYS` — Configures how long entries remain in the
  persistent `seen_ids.sqlite` store.  The default is 7 days.  Older
  entries are purged on startup.  Adjust this value based on how far
  back you want to suppress duplicates.

### New environment variables

To enable and tune the deduplication features, set the following
variables in your `.env` or environment:

```ini
# Refined dedup index (on‑disk)
FEATURE_DEDUP_REFINED=1        # 1=enable persistent signature index

# Persistent seen store
FEATURE_PERSIST_SEEN=1         # 1=record and check item IDs across runs

# In‑memory duplicate suppression TTL (seconds)
SEEN_TTL_SECONDS=86400         # e.g. 86400 for 24 hours

# Persistent duplicate suppression TTL (days)
SEEN_TTL_DAYS=7               # e.g. 7 days
```

If you prefer to rely solely on the signature index and not record
individual IDs, you can set `FEATURE_PERSIST_SEEN=0`.  The
`FEATURE_DEDUP_REFINED` flag defaults to `0` for backwards
compatibility; set it to `1` to activate on‑disk deduplication.

### Runner integration

The `runner._cycle` function now imports `should_filter()` from
`seen_store.py` and calls it at the start of the per‑item loop.
Events whose IDs have been seen recently are skipped and counted as
`skipped_seen`.  The heartbeat metrics include this skip in the
aggregate `skipped` count.

These changes ensure that once an alert has been sent, the bot will
avoid sending the same alert again for the duration of the configured
TTLs.