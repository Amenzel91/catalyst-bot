# Fix Admin Approval Loop Implementation Guide

**Version:** 1.0
**Created:** December 2025
**Priority:** MEDIUM
**Impact:** MEDIUM | **Effort:** MEDIUM | **ROI:** MEDIUM
**Estimated Implementation Time:** 3-4 hours
**Target Files:** `src/catalyst_bot/admin_interactions.py`, `scripts/interaction_server.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [What's Missing](#whats-missing)
4. [Implementation Strategy](#implementation-strategy)
5. [Phase A: Fix Routing Logic](#phase-a-fix-routing-logic)
6. [Phase B: Implement Handlers](#phase-b-implement-handlers)
7. [Phase C: Server Deployment](#phase-c-server-deployment)
8. [Coding Tickets](#coding-tickets)
9. [Testing & Verification](#testing--verification)

---

## Overview

### Problem Statement

The Admin Approval system has **all infrastructure built** but the **interaction loop is broken**:

| Component | Status | Issue |
|-----------|--------|-------|
| Report generation | ✅ Works | `admin_controls.py:761-820` |
| Monte Carlo analysis | ✅ Works | `admin_controls.py:429-518` |
| Parameter recommendations | ✅ Works | `admin_controls.py:520-755` |
| Discord buttons | ✅ Defined | `admin_controls.py:1090-1127` |
| Interaction server | ✅ Exists | `scripts/interaction_server.py` |
| Button handlers | ⚠️ Exists but unreachable | `admin_interactions.py:295-405` |
| **Routing to handlers** | ❌ Broken | Handlers never called |
| **Server auto-start** | ❌ Missing | Manual start required |

### The Broken Loop

```
CURRENT STATE (Broken):
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Admin Report Posted ──────▶ Discord Buttons Displayed       │
│         ✅                           ✅                      │
│                                      │                       │
│                                      ▼                       │
│                              User Clicks Button              │
│                                      │                       │
│                                      ▼                       │
│                              Discord Sends Interaction       │
│                                      │                       │
│                                      ▼                       │
│                      ❌ NO SERVER LISTENING ❌               │
│                                      │                       │
│                              (Nothing Happens)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘

DESIRED STATE (Fixed):
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Admin Report Posted ──────▶ Discord Buttons Displayed       │
│         ✅                           ✅                      │
│                                      │                       │
│                                      ▼                       │
│                              User Clicks Button              │
│                                      │                       │
│                                      ▼                       │
│                      Interaction Server (port 8081)          │
│                                      │                       │
│                                      ▼                       │
│                      admin_interactions.py Handlers          │
│                                      │                       │
│              ┌───────────────────────┼───────────────────┐   │
│              ▼                       ▼                   ▼   │
│         View Details          Approve Changes      Reject    │
│              │                       │               │       │
│              ▼                       ▼               ▼       │
│         Show Embed            Apply Params        Log Only   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Current State Analysis

### 1. Discord Buttons (Working)

**File:** `src/catalyst_bot/admin_controls.py:1090-1127`

```python
def build_admin_components(report_id: str) -> List[Dict[str, Any]]:
    """Build interactive Discord buttons for admin controls."""
    return [
        {
            "type": 1,  # Action Row
            "components": [
                {
                    "type": 2,  # Button
                    "style": 3,  # Success (green)
                    "label": "Approve Changes",
                    "custom_id": f"admin_approve_{report_id}",
                    "emoji": {"name": "✅"},
                },
                {
                    "type": 2,  # Button
                    "style": 4,  # Danger (red)
                    "label": "Reject Changes",
                    "custom_id": f"admin_reject_{report_id}",
                    "emoji": {"name": "❌"},
                },
                # ... more buttons
            ],
        }
    ]
```

### 2. Interaction Server (Exists, Not Running)

**File:** `scripts/interaction_server.py:45-134`

```python
@app.route("/interactions", methods=["POST"])
def handle_interaction():
    """Handle Discord interaction webhooks."""
    # ✅ Signature verification implemented
    # ✅ PING/PONG handling implemented
    # ✅ Routes to handle_interaction() from discord_interactions
    # ❌ But discord_interactions doesn't route to admin handlers!
```

### 3. Admin Handlers (Exist, Never Called)

**File:** `src/catalyst_bot/admin_interactions.py:295-405`

```python
def handle_approve(report_id: str):
    """Handle approve button click."""
    # ✅ Loads report from disk
    # ✅ Applies parameter changes via config_updater
    # ❌ BUT THIS FUNCTION IS NEVER CALLED!

def handle_reject(report_id: str):
    """Handle reject button click."""
    # ✅ Logs rejection
    # ❌ NEVER CALLED

def handle_modal_submit(interaction_data: dict):
    """Handle custom adjustment modal submission."""
    # ✅ Parses modal input
    # ✅ Applies custom parameters
    # ❌ NEVER CALLED
```

### 4. The Routing Bug

**File:** `src/catalyst_bot/admin_interactions.py:249-283`

```python
def handle_admin_interaction(interaction_data: dict) -> dict:
    """Main router for admin interactions."""

    custom_id = interaction_data.get("data", {}).get("custom_id", "")

    # BUG: This MOA check returns BEFORE reaching admin handlers!
    if custom_id.startswith("moa_"):
        return handle_moa_interaction(interaction_data)  # Returns here!

    # Admin routing logic EXISTS but is UNREACHABLE
    # because discord_interactions.py calls handle_interaction()
    # which routes differently...

    if custom_id.startswith("admin_"):
        parts = custom_id.split("_")
        action = parts[1]  # approve, reject, details, custom
        report_id = "_".join(parts[2:])

        if action == "details":
            return build_details_embed(report_id)
        elif action == "approve":
            return handle_approve(report_id)  # UNREACHABLE!
        elif action == "reject":
            return handle_reject(report_id)  # UNREACHABLE!
        elif action == "custom":
            return build_custom_modal(report_id)  # UNREACHABLE!
```

---

## What's Missing

### Critical Gaps

1. **discord_interactions.py doesn't route to admin_interactions.py**
   - File: `src/catalyst_bot/discord_interactions.py:142-388`
   - Routes chart buttons, but NOT admin buttons

2. **Interaction server not auto-started**
   - `scripts/interaction_server.py` must be manually run
   - No systemd service, no Docker config

3. **Discord Application not configured**
   - Interaction endpoint URL not set in Discord Developer Portal

### Parameters That Would Be Applied

From `admin_controls.py:82-117`, the system can adjust:

| Parameter | Type | Range | Purpose |
|-----------|------|-------|---------|
| `MIN_SCORE` | float | 0-1 | Minimum sentiment score |
| `PRICE_CEILING` | float | $1-100 | Max stock price |
| `CONFIDENCE_HIGH` | float | 0-1 | High confidence threshold |
| `MAX_ALERTS_PER_CYCLE` | int | 1-100 | Rate limiting |
| `ANALYZER_HIT_UP_THRESHOLD_PCT` | float | 1-20 | Take profit % |
| Keyword weights | float | 0-2 | Per-category weights |

---

## Implementation Strategy

### Architecture After Fix

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADMIN APPROVAL LOOP                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │ runner.py       │                                            │
│  │ (main process)  │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ├──────────────────────────────────────────┐          │
│           │                                          │          │
│           ▼                                          ▼          │
│  ┌─────────────────┐                      ┌─────────────────┐   │
│  │ interaction_srv │◀─────Discord────────▶│ Discord API     │   │
│  │ (port 8081)     │   Webhooks           │                 │   │
│  └────────┬────────┘                      └─────────────────┘   │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │discord_interact │                                            │
│  │.handle_interact │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ├────────────────────────────────────┐                │
│           │                                    │                │
│           ▼                                    ▼                │
│  ┌─────────────────┐                 ┌─────────────────┐       │
│  │ Chart handlers  │                 │ Admin handlers  │◀─ FIX │
│  │ (existing)      │                 │ (connect these) │       │
│  └─────────────────┘                 └────────┬────────┘       │
│                                               │                 │
│                              ┌────────────────┼────────────────┐│
│                              ▼                ▼                ▼││
│                       ┌──────────┐    ┌──────────┐    ┌────────┐│
│                       │ Approve  │    │ Reject   │    │ Custom ││
│                       │ Changes  │    │ Changes  │    │ Adjust ││
│                       └────┬─────┘    └──────────┘    └────────┘│
│                            │                                    │
│                            ▼                                    │
│                    ┌──────────────┐                             │
│                    │config_updater│                             │
│                    │(apply params)│                             │
│                    └──────────────┘                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase A: Fix Routing Logic

### 1. Update discord_interactions.py

**File:** `src/catalyst_bot/discord_interactions.py`
**Location:** In `handle_interaction()` function (around Line 180)

```python
# MODIFY handle_interaction() to route admin buttons:

def handle_interaction(interaction_data: dict) -> dict:
    """
    Handle Discord interaction webhook.

    Routes to appropriate handler based on custom_id prefix.
    """
    interaction_type = interaction_data.get("type")

    # Handle PING (type 1)
    if interaction_type == 1:
        return {"type": 1}  # PONG

    # Handle component interactions (type 3 = button click)
    if interaction_type == 3:
        custom_id = interaction_data.get("data", {}).get("custom_id", "")

        # Route chart buttons (existing)
        if custom_id.startswith("chart_"):
            return handle_chart_interaction(interaction_data)

        # Route MOA buttons (existing)
        if custom_id.startswith("moa_"):
            from .moa_interaction_handler import handle_moa_interaction
            return handle_moa_interaction(interaction_data)

        # NEW: Route admin buttons
        if custom_id.startswith("admin_"):
            from .admin_interactions import handle_admin_interaction
            return handle_admin_interaction(interaction_data)

        # Unknown button
        log.warning("unknown_button_interaction custom_id=%s", custom_id)
        return {
            "type": 4,  # Channel message with source
            "data": {
                "content": f"Unknown interaction: {custom_id}",
                "flags": 64,  # Ephemeral
            }
        }

    # Handle modal submissions (type 5)
    if interaction_type == 5:
        custom_id = interaction_data.get("data", {}).get("custom_id", "")

        # NEW: Route admin modal submissions
        if custom_id.startswith("admin_custom_modal_"):
            from .admin_interactions import handle_modal_submit
            return handle_modal_submit(interaction_data)

        log.warning("unknown_modal_submission custom_id=%s", custom_id)

    return {"type": 4, "data": {"content": "Interaction not handled", "flags": 64}}
```

### 2. Fix admin_interactions.py Routing

**File:** `src/catalyst_bot/admin_interactions.py`
**Location:** Replace `handle_admin_interaction()` (Lines 216-292)

```python
# Discord response type constants
RESPONSE_TYPE_PONG = 1
RESPONSE_TYPE_MESSAGE = 4
RESPONSE_TYPE_DEFERRED = 5
RESPONSE_TYPE_DEFERRED_UPDATE = 6
RESPONSE_TYPE_UPDATE_MESSAGE = 7
RESPONSE_TYPE_MODAL = 9


def handle_admin_interaction(interaction_data: dict) -> dict:
    """
    Handle admin button interactions.

    Routes based on custom_id format: admin_{action}_{report_id}

    Actions:
        - details: Show detailed breakdown
        - approve: Apply recommended parameters
        - reject: Log rejection, no action
        - custom: Show modal for custom adjustments

    Returns:
        Discord interaction response dict
    """
    custom_id = interaction_data.get("data", {}).get("custom_id", "")

    if not custom_id.startswith("admin_"):
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {"content": "Invalid admin interaction", "flags": 64}
        }

    # Parse custom_id: admin_{action}_{report_id}
    parts = custom_id.split("_", 2)  # Split into max 3 parts
    if len(parts) < 3:
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {"content": "Malformed interaction ID", "flags": 64}
        }

    action = parts[1]  # approve, reject, details, custom
    report_id = parts[2]  # e.g., "2025-12-08"

    log.info("admin_interaction action=%s report_id=%s", action, report_id)

    try:
        if action == "details":
            response_data = build_details_embed(report_id)
            return {"type": RESPONSE_TYPE_MESSAGE, "data": response_data}

        elif action == "approve":
            return handle_approve(report_id)

        elif action == "reject":
            return handle_reject(report_id)

        elif action == "custom":
            modal_response = build_custom_modal(report_id)
            return {"type": RESPONSE_TYPE_MODAL, "data": modal_response}

        else:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {"content": f"Unknown action: {action}", "flags": 64}
            }

    except Exception as e:
        log.error("admin_interaction_failed action=%s err=%s", action, e)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {"content": f"Error: {str(e)}", "flags": 64}
        }
```

---

## Phase B: Implement Handlers

### 1. Enhance handle_approve()

**File:** `src/catalyst_bot/admin_interactions.py`
**Location:** Replace existing `handle_approve()` (Lines 295-324)

```python
def handle_approve(report_id: str) -> dict:
    """
    Handle approve button - apply recommended parameter changes.

    Args:
        report_id: Report identifier (e.g., "2025-12-08")

    Returns:
        Discord response with result
    """
    from .config_updater import apply_parameter_changes, validate_parameter
    from .admin_controls import load_admin_report

    try:
        # Load the report
        report = load_admin_report(report_id)
        if not report:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": f"❌ Report not found: {report_id}",
                    "flags": 64
                }
            }

        # Get recommendations
        recommendations = report.get("recommendations", [])
        if not recommendations:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": "ℹ️ No parameter changes recommended in this report.",
                    "flags": 64
                }
            }

        # Validate all parameters first
        changes_to_apply = {}
        for rec in recommendations:
            param_name = rec.get("parameter")
            new_value = rec.get("recommended_value")

            if param_name and new_value is not None:
                is_valid, error = validate_parameter(param_name, new_value)
                if not is_valid:
                    return {
                        "type": RESPONSE_TYPE_MESSAGE,
                        "data": {
                            "content": f"❌ Invalid parameter: {param_name} = {new_value}\n{error}",
                            "flags": 64
                        }
                    }
                changes_to_apply[param_name] = new_value

        if not changes_to_apply:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": "ℹ️ No valid parameters to apply.",
                    "flags": 64
                }
            }

        # Apply changes
        result = apply_parameter_changes(
            changes=changes_to_apply,
            reason=f"Admin approval from report {report_id}",
            approved_by="discord_admin",
        )

        if result.get("success"):
            applied_list = "\n".join(
                f"• `{k}` → `{v}`"
                for k, v in changes_to_apply.items()
            )
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "embeds": [{
                        "title": "✅ Parameters Applied",
                        "description": f"Successfully applied {len(changes_to_apply)} parameter changes:\n\n{applied_list}",
                        "color": 0x00FF00,  # Green
                        "footer": {"text": f"Report: {report_id}"}
                    }]
                }
            }
        else:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": f"❌ Failed to apply parameters: {result.get('error', 'Unknown error')}",
                    "flags": 64
                }
            }

    except Exception as e:
        log.error("handle_approve_failed report=%s err=%s", report_id, e)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {
                "content": f"❌ Error applying changes: {str(e)}",
                "flags": 64
            }
        }
```

### 2. Enhance handle_reject()

**File:** `src/catalyst_bot/admin_interactions.py`
**Location:** Replace existing `handle_reject()` (Lines 326-336)

```python
def handle_reject(report_id: str) -> dict:
    """
    Handle reject button - log rejection without applying changes.

    Args:
        report_id: Report identifier

    Returns:
        Discord response confirming rejection
    """
    try:
        # Log the rejection
        log.info("admin_changes_rejected report=%s", report_id)

        # Optionally save rejection to tracking
        try:
            from .admin.parameter_manager import log_rejection
            log_rejection(report_id, reason="Manual rejection via Discord")
        except ImportError:
            pass  # Parameter manager not available

        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {
                "embeds": [{
                    "title": "❌ Changes Rejected",
                    "description": f"Parameter recommendations from report `{report_id}` were rejected.\n\nNo changes have been applied.",
                    "color": 0xFF0000,  # Red
                    "footer": {"text": "You can review the report and apply changes manually if needed."}
                }]
            }
        }

    except Exception as e:
        log.error("handle_reject_failed report=%s err=%s", report_id, e)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {
                "content": f"❌ Error logging rejection: {str(e)}",
                "flags": 64
            }
        }
```

### 3. Enhance handle_modal_submit()

**File:** `src/catalyst_bot/admin_interactions.py`
**Location:** Enhance existing `handle_modal_submit()` (Lines 338-405)

```python
def handle_modal_submit(interaction_data: dict) -> dict:
    """
    Handle custom parameter modal submission.

    Parses modal inputs and applies custom parameter values.

    Modal fields:
        - min_score: Minimum sentiment score (0-1)
        - price_ceiling: Maximum stock price ($)
        - confidence_high: High confidence threshold (0-1)
        - max_alerts: Maximum alerts per cycle

    Returns:
        Discord response with result
    """
    from .config_updater import apply_parameter_changes, validate_parameter

    try:
        custom_id = interaction_data.get("data", {}).get("custom_id", "")
        components = interaction_data.get("data", {}).get("components", [])

        # Parse report_id from custom_id: admin_custom_modal_{report_id}
        parts = custom_id.split("_")
        report_id = parts[-1] if len(parts) > 3 else "unknown"

        # Extract values from modal components
        values = {}
        for row in components:
            for component in row.get("components", []):
                field_id = component.get("custom_id", "")
                value = component.get("value", "")
                if field_id and value:
                    values[field_id] = value

        # Map modal fields to parameters
        param_mapping = {
            "min_score": ("MIN_SCORE", float),
            "price_ceiling": ("PRICE_CEILING", float),
            "confidence_high": ("CONFIDENCE_HIGH", float),
            "max_alerts": ("MAX_ALERTS_PER_CYCLE", int),
        }

        changes_to_apply = {}
        errors = []

        for field_id, (param_name, cast_type) in param_mapping.items():
            if field_id in values and values[field_id].strip():
                try:
                    parsed_value = cast_type(values[field_id])
                    is_valid, error = validate_parameter(param_name, parsed_value)
                    if is_valid:
                        changes_to_apply[param_name] = parsed_value
                    else:
                        errors.append(f"{param_name}: {error}")
                except ValueError:
                    errors.append(f"{field_id}: Invalid number format")

        if errors:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": f"❌ Validation errors:\n" + "\n".join(errors),
                    "flags": 64
                }
            }

        if not changes_to_apply:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": "ℹ️ No parameters specified. Nothing to change.",
                    "flags": 64
                }
            }

        # Apply changes
        result = apply_parameter_changes(
            changes=changes_to_apply,
            reason=f"Custom adjustment from modal (report {report_id})",
            approved_by="discord_admin_custom",
        )

        if result.get("success"):
            applied_list = "\n".join(
                f"• `{k}` → `{v}`"
                for k, v in changes_to_apply.items()
            )
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "embeds": [{
                        "title": "✅ Custom Parameters Applied",
                        "description": f"Applied custom adjustments:\n\n{applied_list}",
                        "color": 0x00FF00,
                    }]
                }
            }
        else:
            return {
                "type": RESPONSE_TYPE_MESSAGE,
                "data": {
                    "content": f"❌ Failed: {result.get('error', 'Unknown error')}",
                    "flags": 64
                }
            }

    except Exception as e:
        log.error("handle_modal_submit_failed err=%s", e)
        return {
            "type": RESPONSE_TYPE_MESSAGE,
            "data": {
                "content": f"❌ Error processing modal: {str(e)}",
                "flags": 64
            }
        }
```

---

## Phase C: Server Deployment

### 1. Update Interaction Server

**File:** `scripts/interaction_server.py`
**Location:** Ensure proper routing (around Line 100)

```python
# Verify this section routes to discord_interactions correctly:

@app.route("/interactions", methods=["POST"])
def handle_discord_interaction():
    """Handle Discord interaction webhook."""

    # Verify signature
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")

    if not verify_discord_signature(signature, timestamp, request.data):
        return "Invalid signature", 401

    interaction_data = request.json

    # Route to main handler (which now routes to admin handlers)
    from catalyst_bot.discord_interactions import handle_interaction
    response = handle_interaction(interaction_data)

    return jsonify(response)
```

### 2. Create Systemd Service (Linux)

**File:** `services/interaction_server.service`

```ini
[Unit]
Description=Catalyst-Bot Discord Interaction Server
After=network.target

[Service]
Type=simple
User=catalyst
WorkingDirectory=/home/catalyst/catalyst-bot
Environment=PYTHONPATH=/home/catalyst/catalyst-bot/src
ExecStart=/home/catalyst/catalyst-bot/venv/bin/python scripts/interaction_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Add to Bot Startup (Alternative)

**File:** `src/catalyst_bot/runner.py`
**Location:** In `runner_main()` after health server

```python
# Option: Start interaction server in subprocess
if os.getenv("FEATURE_ADMIN_INTERACTIONS", "1").strip().lower() in ("1", "true", "yes"):
    try:
        import subprocess
        import sys

        interaction_server = subprocess.Popen(
            [sys.executable, "scripts/interaction_server.py"],
            cwd=str(Path(__file__).parent.parent.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log.info("interaction_server_started pid=%d", interaction_server.pid)

        # Register cleanup
        import atexit
        atexit.register(lambda: interaction_server.terminate())

    except Exception as e:
        log.warning("interaction_server_start_failed err=%s", e)
```

---

## Coding Tickets

### Phase A: Fix Routing

#### Ticket A.1: Update discord_interactions.py Routing
```
Title: Add admin button routing to discord_interactions.py
Priority: Critical
Estimate: 30 minutes

File: src/catalyst_bot/discord_interactions.py
Location: handle_interaction() ~Line 180

Tasks:
1. Add check for custom_id.startswith("admin_")
2. Import and call handle_admin_interaction()
3. Add modal submission routing for admin_custom_modal_
4. Test routing logic

Acceptance Criteria:
- [ ] Admin buttons routed to admin_interactions.py
- [ ] Modal submissions handled
- [ ] Unknown buttons logged
```

#### Ticket A.2: Fix admin_interactions.py Router
```
Title: Fix handle_admin_interaction() routing logic
Priority: Critical
Estimate: 30 minutes

File: src/catalyst_bot/admin_interactions.py
Location: handle_admin_interaction() Lines 216-292

Tasks:
1. Fix custom_id parsing (split on underscore)
2. Route to correct handler (details, approve, reject, custom)
3. Add proper error handling
4. Add logging

Acceptance Criteria:
- [ ] All four actions route correctly
- [ ] Errors return user-friendly messages
- [ ] Actions logged
```

### Phase B: Implement Handlers

#### Ticket B.1: Enhance handle_approve()
```
Title: Complete approve handler with parameter application
Priority: High
Estimate: 45 minutes

File: src/catalyst_bot/admin_interactions.py
Location: handle_approve() Lines 295-324

Tasks:
1. Load report from disk
2. Extract recommendations
3. Validate all parameters
4. Apply via config_updater
5. Return success/failure embed

Acceptance Criteria:
- [ ] Loads correct report
- [ ] Validates parameters before applying
- [ ] Creates .env backup
- [ ] Returns formatted embed with changes
```

#### Ticket B.2: Enhance handle_reject()
```
Title: Complete reject handler with logging
Priority: Medium
Estimate: 20 minutes

File: src/catalyst_bot/admin_interactions.py
Location: handle_reject() Lines 326-336

Tasks:
1. Log rejection with report_id
2. Optionally save to tracking database
3. Return confirmation embed

Acceptance Criteria:
- [ ] Rejection logged
- [ ] User sees confirmation message
```

#### Ticket B.3: Enhance handle_modal_submit()
```
Title: Complete modal submission handler
Priority: Medium
Estimate: 30 minutes

File: src/catalyst_bot/admin_interactions.py
Location: handle_modal_submit() Lines 338-405

Tasks:
1. Parse modal components
2. Validate each parameter
3. Apply changes
4. Return result

Acceptance Criteria:
- [ ] Modal values parsed correctly
- [ ] Validation errors shown to user
- [ ] Changes applied when valid
```

### Phase C: Deployment

#### Ticket C.1: Create Systemd Service
```
Title: Create systemd service for interaction server
Priority: High
Estimate: 30 minutes

Files to Create:
- services/interaction_server.service

Tasks:
1. Create service file
2. Document installation steps
3. Add to deployment docs

Acceptance Criteria:
- [ ] Service file created
- [ ] Can be installed with systemctl
- [ ] Auto-restarts on failure
```

#### Ticket C.2: Document Discord Setup
```
Title: Document Discord Application configuration
Priority: High
Estimate: 30 minutes

Tasks:
1. Document how to set Interaction Endpoint URL in Discord
2. Document required environment variables
3. Add to deployment checklist

Acceptance Criteria:
- [ ] Clear instructions for Discord setup
- [ ] All env vars documented
```

---

## Testing & Verification

### 1. Unit Tests

```python
# tests/test_admin_interactions.py
import pytest

def test_admin_interaction_routing():
    """Test admin interaction routing logic."""
    from catalyst_bot.admin_interactions import handle_admin_interaction

    # Test approve routing
    interaction = {
        "data": {
            "custom_id": "admin_approve_2025-12-08"
        }
    }
    # Should not crash (actual approval will fail without report)
    response = handle_admin_interaction(interaction)
    assert "type" in response

def test_custom_id_parsing():
    """Test custom_id parsing."""
    custom_id = "admin_approve_2025-12-08"
    parts = custom_id.split("_", 2)

    assert parts[0] == "admin"
    assert parts[1] == "approve"
    assert parts[2] == "2025-12-08"
```

### 2. Integration Test

```bash
# Test interaction routing end-to-end
python -c "
from catalyst_bot.discord_interactions import handle_interaction

# Simulate button click
interaction = {
    'type': 3,  # Button click
    'data': {
        'custom_id': 'admin_details_2025-12-08'
    }
}

response = handle_interaction(interaction)
print(f'Response type: {response.get(\"type\")}')
print(f'Response: {response}')
"
```

### 3. Manual Testing Checklist

```
[ ] Start interaction server: python scripts/interaction_server.py
[ ] Verify health endpoint: curl http://localhost:8081/health
[ ] Post admin report to Discord (should have buttons)
[ ] Click "View Details" button → Should show detailed embed
[ ] Click "Approve Changes" button → Should apply parameters
[ ] Click "Reject Changes" button → Should show rejection message
[ ] Click "Custom Adjust" button → Should show modal
[ ] Submit modal → Should apply custom values
```

### 4. Discord Setup Verification

```bash
# Required environment variables
echo "DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN:+SET}"
echo "DISCORD_PUBLIC_KEY: ${DISCORD_PUBLIC_KEY:+SET}"
echo "DISCORD_ADMIN_CHANNEL_ID: ${DISCORD_ADMIN_CHANNEL_ID:+SET}"
echo "FEATURE_ADMIN_REPORTS: ${FEATURE_ADMIN_REPORTS:-1}"
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Bot token for posting messages |
| `DISCORD_PUBLIC_KEY` | Yes | For signature verification |
| `DISCORD_ADMIN_CHANNEL_ID` | Yes | Channel for admin reports |
| `FEATURE_ADMIN_REPORTS` | No | Enable admin reports (default: 1) |
| `FEATURE_ADMIN_INTERACTIONS` | No | Enable interaction server (default: 1) |
| `INTERACTION_SERVER_PORT` | No | Port for interaction server (default: 8081) |

---

## Deployment Checklist

1. **Code Changes:**
   - [ ] Update discord_interactions.py routing
   - [ ] Fix admin_interactions.py handlers
   - [ ] Test locally with mock interactions

2. **Discord Application Setup:**
   - [ ] Go to Discord Developer Portal
   - [ ] Navigate to your application
   - [ ] Set "Interactions Endpoint URL" to `https://your-domain.com/interactions`
   - [ ] Ensure URL is publicly accessible (HTTPS required)

3. **Server Deployment:**
   - [ ] Deploy interaction server (systemd, Docker, or subprocess)
   - [ ] Set up reverse proxy (nginx/cloudflare) for HTTPS
   - [ ] Verify health endpoint accessible

4. **Verification:**
   - [ ] Post test admin report
   - [ ] Click each button type
   - [ ] Verify parameters applied correctly

---

## Summary

This implementation fixes:

1. **Routing Bug** - Connect discord_interactions.py → admin_interactions.py
2. **Handler Completion** - Full approve/reject/custom handlers
3. **Server Deployment** - Systemd service for production

**Implementation Order:**
1. Phase A: Fix routing logic (1 hour)
2. Phase B: Implement handlers (1.5 hours)
3. Phase C: Server deployment (1 hour)

**Expected Impact:**
- Admin can approve/reject parameter changes from Discord
- Close the feedback loop for data-driven optimization
- Reduce manual intervention required

---

**End of Implementation Guide**
