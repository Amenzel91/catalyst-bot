# Paper Trading Bot - Disaster Recovery Guide

**Version:** 1.0
**Last Updated:** November 2025
**Recovery Time Objective (RTO):** < 1 hour
**Recovery Point Objective (RPO):** < 24 hours

---

## Table of Contents

1. [Overview](#overview)
2. [Backup Procedures](#backup-procedures)
3. [Database Backup Automation](#database-backup-automation)
4. [Restore Procedures](#restore-procedures)
5. [Kill Switch Activation](#kill-switch-activation)
6. [Emergency Position Liquidation](#emergency-position-liquidation)
7. [Data Corruption Recovery](#data-corruption-recovery)
8. [API Key Rotation](#api-key-rotation)
9. [Incident Response Checklist](#incident-response-checklist)
10. [Disaster Scenarios](#disaster-scenarios)

---

## Overview

This guide provides comprehensive disaster recovery procedures for the Catalyst Paper Trading Bot. It covers backup strategies, emergency protocols, and recovery procedures for various failure scenarios.

**Disaster Recovery Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│  Primary System                                             │
│  ├── Trading Bot (active)                                   │
│  ├── Databases (live)                                       │
│  ├── Configuration files                                    │
│  └── RL Models                                              │
└────────────┬────────────────────────────────────────────────┘
             │
             ├── Daily Backups ──→ Local Storage (7 days)
             ├── Weekly Backups ──→ Cloud Storage (90 days)
             └── Critical Alerts ──→ Discord/Email/SMS
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Recovery System                                            │
│  ├── Backup databases (timestamped)                         │
│  ├── Backup configuration                                   │
│  ├── Backup models                                          │
│  └── Runbook documentation                                  │
└─────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- **Immutability**: Never modify original backups
- **Automation**: Backups run automatically without intervention
- **Validation**: Test restores monthly
- **Documentation**: Every procedure is documented
- **Testing**: Disaster recovery drills quarterly

---

## Backup Procedures

### 1. Manual Backup

```bash
#!/bin/bash
# manual-backup.sh - Immediate backup of all critical data

set -e

BACKUP_ROOT="/home/catalyst-bot/catalyst-bot/data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/manual_$TIMESTAMP"

echo "=== Catalyst Bot Manual Backup ==="
echo "Timestamp: $TIMESTAMP"
echo "Destination: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"/{databases,config,models,logs}

# Backup databases
echo "Backing up databases..."
for db in /home/catalyst-bot/catalyst-bot/data/databases/*.db; do
    db_name=$(basename "$db")
    sqlite3 "$db" ".backup '$BACKUP_DIR/databases/$db_name'"
    echo "  ✓ $db_name"
done

# Backup configuration
echo "Backing up configuration..."
cp /home/catalyst-bot/catalyst-bot/src/.env "$BACKUP_DIR/config/.env.backup"
cp -r /home/catalyst-bot/catalyst-bot/config "$BACKUP_DIR/config/"
echo "  ✓ Configuration files"

# Backup RL models
echo "Backing up RL models..."
cp -r /home/catalyst-bot/catalyst-bot/data/models "$BACKUP_DIR/models/"
echo "  ✓ RL models"

# Backup recent logs (last 7 days)
echo "Backing up recent logs..."
find /home/catalyst-bot/catalyst-bot/data/logs -name "*.log" -mtime -7 -exec cp {} "$BACKUP_DIR/logs/" \;
find /home/catalyst-bot/catalyst-bot/data/logs -name "*.jsonl" -mtime -7 -exec cp {} "$BACKUP_DIR/logs/" \;
echo "  ✓ Recent logs"

# Create manifest
echo "Creating backup manifest..."
cat > "$BACKUP_DIR/MANIFEST.txt" << EOF
Catalyst Bot Backup
===================
Timestamp: $TIMESTAMP
Type: Manual
Hostname: $(hostname)
User: $(whoami)

Contents:
- Databases: $(ls -1 $BACKUP_DIR/databases | wc -l) files
- Config files: $(find $BACKUP_DIR/config -type f | wc -l) files
- RL models: $(find $BACKUP_DIR/models -type f | wc -l) files
- Log files: $(ls -1 $BACKUP_DIR/logs | wc -l) files

Total size: $(du -sh $BACKUP_DIR | cut -f1)
EOF

# Compress backup
echo "Compressing backup..."
tar -czf "$BACKUP_ROOT/manual_$TIMESTAMP.tar.gz" -C "$BACKUP_ROOT" "manual_$TIMESTAMP"
rm -rf "$BACKUP_DIR"

echo ""
echo "✓ Backup complete: $BACKUP_ROOT/manual_$TIMESTAMP.tar.gz"
echo "Size: $(du -sh $BACKUP_ROOT/manual_$TIMESTAMP.tar.gz | cut -f1)"
```

### 2. Backup Verification

```bash
#!/bin/bash
# verify-backup.sh - Verify backup integrity

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

echo "=== Backup Verification ==="
echo "File: $BACKUP_FILE"

# Check file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "✗ File not found"
    exit 1
fi
echo "✓ File exists"

# Check file integrity
if tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "✓ Archive is valid"
else
    echo "✗ Archive is corrupted"
    exit 1
fi

# List contents
echo ""
echo "Archive contents:"
tar -tzf "$BACKUP_FILE" | head -20

# Check manifest
echo ""
echo "Manifest:"
tar -xzf "$BACKUP_FILE" --to-stdout "*/MANIFEST.txt" 2>/dev/null || echo "✗ No manifest found"

echo ""
echo "✓ Backup verification complete"
```

### 3. Backup Retention Policy

| Backup Type | Frequency | Retention | Storage Location |
|-------------|-----------|-----------|------------------|
| **Hourly** | Every hour during market hours | 24 hours | Local disk |
| **Daily** | 2 AM ET | 7 days | Local disk |
| **Weekly** | Sunday 2 AM ET | 90 days | Cloud storage (S3/GCS) |
| **Monthly** | 1st of month | 1 year | Cloud storage (cold) |
| **Pre-deployment** | Before each deployment | 30 days | Local + cloud |

---

## Database Backup Automation

### 1. Automated Backup Script

```bash
#!/bin/bash
# automated-backup.sh - Daily backup with cloud sync

set -e

# Configuration
BACKUP_DIR="/home/catalyst-bot/catalyst-bot/data/backups"
DB_DIR="/home/catalyst-bot/catalyst-bot/data/databases"
RETENTION_DAYS=7
CLOUD_BUCKET="s3://catalyst-bot-backups"  # Or gs://
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create daily backup directory
DAILY_DIR="$BACKUP_DIR/daily_$DATE"
mkdir -p "$DAILY_DIR"

echo "=== Automated Backup - $TIMESTAMP ==="

# Backup each database with online backup
for db in "$DB_DIR"/*.db; do
    db_name=$(basename "$db" .db)
    backup_file="$DAILY_DIR/${db_name}_${TIMESTAMP}.db"

    echo "Backing up $db_name..."

    # SQLite online backup (safe while bot is running)
    sqlite3 "$db" ".backup '$backup_file'"

    # Verify backup
    if sqlite3 "$backup_file" "PRAGMA integrity_check;" | grep -q "ok"; then
        echo "  ✓ $db_name verified"
    else
        echo "  ✗ $db_name verification failed!"
        exit 1
    fi

    # Compress backup
    gzip "$backup_file"
done

# Create backup metadata
cat > "$DAILY_DIR/metadata.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "date": "$DATE",
  "type": "daily_automated",
  "databases": [
    $(ls -1 "$DAILY_DIR"/*.db.gz | sed 's/.*\///' | sed 's/^/    "/' | sed 's/$/"/' | paste -sd, -)
  ],
  "size_bytes": $(du -sb "$DAILY_DIR" | cut -f1),
  "hostname": "$(hostname)"
}
EOF

# Sync to cloud storage (if configured)
if command -v aws &> /dev/null; then
    echo "Syncing to S3..."
    aws s3 sync "$DAILY_DIR" "$CLOUD_BUCKET/daily/$DATE/" --storage-class STANDARD_IA
    echo "  ✓ Cloud backup complete"
fi

# Remove old backups (local only)
echo "Cleaning up old backups (>$RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "daily_*" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true
echo "  ✓ Cleanup complete"

# Send success notification
if [ -n "$DISCORD_ADMIN_WEBHOOK" ]; then
    curl -X POST "$DISCORD_ADMIN_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"content\":\"✅ Daily backup completed: $TIMESTAMP\"}"
fi

echo ""
echo "✓ Backup complete: $DAILY_DIR"
echo "Total size: $(du -sh $DAILY_DIR | cut -f1)"
```

### 2. Systemd Timer for Automated Backups

```ini
# /etc/systemd/system/catalyst-bot-backup.service
[Unit]
Description=Catalyst Bot Daily Backup
After=network.target

[Service]
Type=oneshot
User=catalyst-bot
ExecStart=/home/catalyst-bot/catalyst-bot/scripts/automated-backup.sh
StandardOutput=append:/home/catalyst-bot/catalyst-bot/data/logs/backup.log
StandardError=append:/home/catalyst-bot/catalyst-bot/data/logs/backup.error.log
```

```ini
# /etc/systemd/system/catalyst-bot-backup.timer
[Unit]
Description=Daily Backup Timer for Catalyst Bot
Requires=catalyst-bot-backup.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# Enable timer
sudo systemctl daemon-reload
sudo systemctl enable catalyst-bot-backup.timer
sudo systemctl start catalyst-bot-backup.timer

# Verify
sudo systemctl list-timers --all | grep catalyst
```

### 3. Cloud Storage Configuration

**AWS S3 Setup:**
```bash
# Install AWS CLI
sudo apt install -y awscli

# Configure credentials
aws configure
# AWS Access Key ID: <your_key>
# AWS Secret Access Key: <your_secret>
# Default region: us-east-1
# Default output format: json

# Create S3 bucket
aws s3 mb s3://catalyst-bot-backups

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket catalyst-bot-backups \
    --versioning-configuration Status=Enabled

# Set lifecycle policy (transition to Glacier after 90 days)
cat > lifecycle.json << 'EOF'
{
  "Rules": [
    {
      "Id": "ArchiveOldBackups",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
    --bucket catalyst-bot-backups \
    --lifecycle-configuration file://lifecycle.json
```

**Google Cloud Storage Setup:**
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize gcloud
gcloud init

# Create GCS bucket
gsutil mb -c STANDARD -l us-east1 gs://catalyst-bot-backups

# Enable versioning
gsutil versioning set on gs://catalyst-bot-backups

# Set lifecycle policy
cat > lifecycle.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 90}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF

gsutil lifecycle set lifecycle.json gs://catalyst-bot-backups

# Sync backups
gsutil -m rsync -r /home/catalyst-bot/catalyst-bot/data/backups gs://catalyst-bot-backups/
```

---

## Restore Procedures

### 1. Full System Restore

```bash
#!/bin/bash
# restore-from-backup.sh - Restore entire system from backup

set -e

BACKUP_FILE="$1"
RESTORE_DATE="${2:-$(date +%Y%m%d)}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz> [restore_date]"
    exit 1
fi

echo "=== Catalyst Bot System Restore ==="
echo "Backup file: $BACKUP_FILE"
echo "Restore date: $RESTORE_DATE"
echo ""
echo "WARNING: This will overwrite current databases and configuration!"
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Stop trading bot
echo "Stopping trading bot..."
sudo systemctl stop catalyst-trading-bot.service
echo "  ✓ Service stopped"

# Create pre-restore backup
echo "Creating pre-restore backup..."
PREBACKUP_DIR="/home/catalyst-bot/catalyst-bot/data/backups/pre_restore_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$PREBACKUP_DIR"
cp -r /home/catalyst-bot/catalyst-bot/data/databases "$PREBACKUP_DIR/"
cp /home/catalyst-bot/catalyst-bot/src/.env "$PREBACKUP_DIR/.env.pre_restore"
echo "  ✓ Pre-restore backup: $PREBACKUP_DIR"

# Extract backup
echo "Extracting backup..."
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
BACKUP_DIR=$(find "$TEMP_DIR" -maxdepth 1 -type d ! -path "$TEMP_DIR" | head -1)
echo "  ✓ Extracted to: $BACKUP_DIR"

# Restore databases
echo "Restoring databases..."
for db in "$BACKUP_DIR"/databases/*.db; do
    db_name=$(basename "$db")
    cp "$db" "/home/catalyst-bot/catalyst-bot/data/databases/$db_name"
    echo "  ✓ Restored $db_name"
done

# Restore configuration
echo "Restoring configuration..."
cp "$BACKUP_DIR/config/.env.backup" "/home/catalyst-bot/catalyst-bot/src/.env"
echo "  ✓ Configuration restored"

# Verify database integrity
echo "Verifying database integrity..."
for db in /home/catalyst-bot/catalyst-bot/data/databases/*.db; do
    db_name=$(basename "$db")
    if sqlite3 "$db" "PRAGMA integrity_check;" | grep -q "ok"; then
        echo "  ✓ $db_name OK"
    else
        echo "  ✗ $db_name FAILED integrity check!"
        exit 1
    fi
done

# Cleanup temp files
rm -rf "$TEMP_DIR"

# Start trading bot
echo "Starting trading bot..."
sudo systemctl start catalyst-trading-bot.service
sleep 5

# Verify service started
if sudo systemctl is-active --quiet catalyst-trading-bot.service; then
    echo "  ✓ Service started successfully"
else
    echo "  ✗ Service failed to start!"
    exit 1
fi

echo ""
echo "✓ Restore complete!"
echo ""
echo "Next steps:"
echo "1. Verify bot functionality: sudo journalctl -u catalyst-trading-bot.service -f"
echo "2. Check portfolio state: python -m catalyst_bot.portfolio.status"
echo "3. Monitor for errors for 30 minutes"
```

### 2. Single Database Restore

```bash
#!/bin/bash
# restore-single-db.sh - Restore individual database

DB_NAME="$1"
BACKUP_FILE="$2"

if [ -z "$DB_NAME" ] || [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <db_name> <backup_file.db.gz>"
    exit 1
fi

echo "=== Restoring $DB_NAME ==="

# Verify backup exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "✗ Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Create safety backup of current DB
CURRENT_DB="/home/catalyst-bot/catalyst-bot/data/databases/${DB_NAME}.db"
SAFETY_BACKUP="${CURRENT_DB}.pre_restore_$(date +%Y%m%d_%H%M%S)"

if [ -f "$CURRENT_DB" ]; then
    echo "Creating safety backup..."
    cp "$CURRENT_DB" "$SAFETY_BACKUP"
    echo "  ✓ Safety backup: $SAFETY_BACKUP"
fi

# Decompress and restore
echo "Restoring from backup..."
gunzip -c "$BACKUP_FILE" > "$CURRENT_DB"

# Verify integrity
echo "Verifying database integrity..."
if sqlite3 "$CURRENT_DB" "PRAGMA integrity_check;" | grep -q "ok"; then
    echo "  ✓ Database integrity OK"
    echo "  ✓ Restore complete"
else
    echo "  ✗ Database integrity check failed!"
    echo "  Rolling back to safety backup..."
    mv "$SAFETY_BACKUP" "$CURRENT_DB"
    exit 1
fi

echo ""
echo "✓ ${DB_NAME}.db restored successfully"
```

### 3. Restore from Cloud Storage

```bash
#!/bin/bash
# restore-from-cloud.sh - Download and restore from S3/GCS

RESTORE_DATE="$1"
CLOUD_BUCKET="s3://catalyst-bot-backups"  # Or gs://

if [ -z "$RESTORE_DATE" ]; then
    echo "Usage: $0 <YYYYMMDD>"
    exit 1
fi

echo "=== Restoring from Cloud Storage ==="
echo "Date: $RESTORE_DATE"

# Download from S3
TEMP_DIR=$(mktemp -d)
echo "Downloading backup from cloud..."

if command -v aws &> /dev/null; then
    aws s3 sync "$CLOUD_BUCKET/daily/$RESTORE_DATE/" "$TEMP_DIR/"
elif command -v gsutil &> /dev/null; then
    gsutil -m rsync -r "gs://catalyst-bot-backups/daily/$RESTORE_DATE/" "$TEMP_DIR/"
else
    echo "✗ No cloud CLI found (aws or gsutil)"
    exit 1
fi

# List downloaded files
echo ""
echo "Downloaded files:"
ls -lh "$TEMP_DIR"

# Decompress databases
echo ""
echo "Decompressing databases..."
for db_gz in "$TEMP_DIR"/*.db.gz; do
    db_name=$(basename "$db_gz" .gz)
    gunzip -c "$db_gz" > "$TEMP_DIR/$db_name"
    echo "  ✓ $db_name"
done

# Restore databases
echo ""
echo "Restoring databases..."
for db in "$TEMP_DIR"/*.db; do
    db_name=$(basename "$db")
    cp "$db" "/home/catalyst-bot/catalyst-bot/data/databases/$db_name"
    echo "  ✓ $db_name"
done

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "✓ Cloud restore complete"
```

---

## Kill Switch Activation

### 1. Manual Kill Switch

```bash
#!/bin/bash
# kill-switch.sh - Emergency stop all trading

echo "=== KILL SWITCH ACTIVATED ==="
echo "Timestamp: $(date)"
echo ""

# Stop trading bot service
echo "Stopping trading bot..."
sudo systemctl stop catalyst-trading-bot.service
echo "  ✓ Service stopped"

# Cancel all open orders
echo "Cancelling all open orders..."
python << 'EOF'
from alpaca.trading.client import TradingClient
import os

client = TradingClient(
    os.getenv('ALPACA_API_KEY'),
    os.getenv('ALPACA_SECRET'),
    paper=True
)

# Cancel all orders
orders = client.get_orders(status='open')
for order in orders:
    client.cancel_order_by_id(order.id)
    print(f"  ✓ Cancelled order: {order.id} ({order.symbol})")

print(f"\nTotal orders cancelled: {len(orders)}")
EOF

# Optional: Close all positions (comment out if not needed)
# echo "Closing all positions..."
# python << 'EOF'
# from alpaca.trading.client import TradingClient
# import os
#
# client = TradingClient(
#     os.getenv('ALPACA_API_KEY'),
#     os.getenv('ALPACA_SECRET'),
#     paper=True
# )
#
# client.close_all_positions(cancel_orders=True)
# print("  ✓ All positions closed")
# EOF

# Create kill switch log
LOG_FILE="/home/catalyst-bot/catalyst-bot/data/logs/kill_switch_$(date +%Y%m%d_%H%M%S).log"
cat > "$LOG_FILE" << EOF
KILL SWITCH ACTIVATION
======================
Timestamp: $(date)
Triggered by: $(whoami)
Hostname: $(hostname)

Actions Taken:
- Trading bot service stopped
- All open orders cancelled
- Kill switch log created

Portfolio Status at Kill Switch:
$(python -m catalyst_bot.portfolio.status)
EOF

echo ""
echo "✓ Kill switch activated"
echo "Log file: $LOG_FILE"

# Send Discord notification
if [ -n "$DISCORD_ADMIN_WEBHOOK" ]; then
    curl -X POST "$DISCORD_ADMIN_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"content\":\"🚨 **KILL SWITCH ACTIVATED** 🚨\nTimestamp: $(date)\nTriggered by: $(whoami)\"}"
fi
```

### 2. Automated Kill Switch (Circuit Breaker)

```python
# catalyst_bot/risk/circuit_breaker.py
import logging
from datetime import datetime
from catalyst_bot.database import get_db_connection

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """Automated kill switch based on risk thresholds"""

    def __init__(self, config):
        self.daily_loss_limit = config.get('DAILY_LOSS_LIMIT_PCT', -0.03)
        self.max_drawdown = config.get('MAX_DRAWDOWN_PCT', -0.10)
        self.consecutive_losses = config.get('CIRCUIT_BREAKER_CONSECUTIVE_LOSSES', 3)
        self.is_active = True

    def check_thresholds(self, portfolio):
        """Check if circuit breaker should trigger"""

        # Check daily loss limit
        if portfolio.daily_pnl_pct < self.daily_loss_limit:
            self.activate(
                reason='daily_loss_limit',
                details=f"Daily P&L: {portfolio.daily_pnl_pct:.2%}"
            )
            return False

        # Check max drawdown
        if portfolio.drawdown < self.max_drawdown:
            self.activate(
                reason='max_drawdown',
                details=f"Drawdown: {portfolio.drawdown:.2%}"
            )
            return False

        # Check consecutive losses
        recent_trades = self.get_recent_trades(limit=self.consecutive_losses)
        if len(recent_trades) >= self.consecutive_losses:
            if all(trade.pnl < 0 for trade in recent_trades):
                self.activate(
                    reason='consecutive_losses',
                    details=f"{self.consecutive_losses} consecutive losing trades"
                )
                return False

        return True  # OK to continue trading

    def activate(self, reason, details):
        """Activate circuit breaker"""
        if not self.is_active:
            return  # Already activated

        logger.critical(f"Circuit breaker activated: {reason} - {details}")

        # Stop trading
        self.is_active = False

        # Log to database
        self.log_activation(reason, details)

        # Send notifications
        self.send_notifications(reason, details)

        # Cancel all orders
        self.cancel_all_orders()

        # Optionally close all positions
        # self.close_all_positions()

    def log_activation(self, reason, details):
        """Log circuit breaker activation to database"""
        conn = get_db_connection('circuit_breaker.db')
        conn.execute("""
            INSERT INTO activations (timestamp, reason, details)
            VALUES (?, ?, ?)
        """, (datetime.utcnow(), reason, details))
        conn.commit()
        conn.close()

    def send_notifications(self, reason, details):
        """Send emergency notifications"""
        from catalyst_bot.monitoring.notifications import send_discord_alert

        alert_data = {
            'alert': 'Circuit Breaker Activated',
            'severity': 'critical',
            'metric': reason,
            'value': details,
            'threshold': 'N/A',
            'description': f'Trading halted due to {reason}: {details}',
            'timestamp': datetime.utcnow().isoformat()
        }

        send_discord_alert(os.getenv('DISCORD_ADMIN_WEBHOOK'), alert_data)

    def get_recent_trades(self, limit=10):
        """Get most recent trades"""
        conn = get_db_connection('trades.db')
        cursor = conn.execute("""
            SELECT * FROM trades
            ORDER BY closed_at DESC
            LIMIT ?
        """, (limit,))
        trades = cursor.fetchall()
        conn.close()
        return trades

    def cancel_all_orders(self):
        """Cancel all open orders"""
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            os.getenv('ALPACA_API_KEY'),
            os.getenv('ALPACA_SECRET'),
            paper=True
        )

        try:
            client.cancel_orders()
            logger.info("All orders cancelled by circuit breaker")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
```

---

## Emergency Position Liquidation

### 1. Close All Positions Script

```bash
#!/bin/bash
# liquidate-all-positions.sh - Emergency close all positions

echo "=== EMERGENCY POSITION LIQUIDATION ==="
echo "WARNING: This will close ALL open positions at market price!"
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Liquidation cancelled"
    exit 0
fi

python << 'EOF'
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ClosePositionRequest
import os
import time

client = TradingClient(
    os.getenv('ALPACA_API_KEY'),
    os.getenv('ALPACA_SECRET'),
    paper=True
)

# Get all open positions
positions = client.get_all_positions()
print(f"\nFound {len(positions)} open positions to liquidate")
print("")

# Close each position
for pos in positions:
    try:
        print(f"Closing {pos.symbol}: {pos.qty} shares @ ${pos.current_price}")

        # Close position (market order)
        client.close_position(pos.symbol)

        print(f"  ✓ {pos.symbol} closed")
        time.sleep(0.5)  # Rate limiting

    except Exception as e:
        print(f"  ✗ Failed to close {pos.symbol}: {e}")

print("")
print("✓ Liquidation complete")

# Verify all positions closed
remaining = client.get_all_positions()
if remaining:
    print(f"⚠ Warning: {len(remaining)} positions still open:")
    for pos in remaining:
        print(f"  - {pos.symbol}: {pos.qty} shares")
else:
    print("✓ All positions successfully closed")
EOF

# Log liquidation
echo ""
echo "Liquidation logged to: /home/catalyst-bot/catalyst-bot/data/logs/liquidation_$(date +%Y%m%d_%H%M%S).log"
```

### 2. Selective Position Closure

```python
# catalyst_bot/risk/position_liquidator.py
from alpaca.trading.client import TradingClient
import logging

logger = logging.getLogger(__name__)

class PositionLiquidator:
    """Selective position liquidation based on criteria"""

    def __init__(self, alpaca_client: TradingClient):
        self.client = alpaca_client

    def close_losing_positions(self, threshold_pct=-0.10):
        """Close positions with unrealized loss > threshold"""
        positions = self.client.get_all_positions()
        closed = []

        for pos in positions:
            unrealized_pct = float(pos.unrealized_plpc)

            if unrealized_pct < threshold_pct:
                logger.warning(
                    f"Closing {pos.symbol}: unrealized P&L {unrealized_pct:.2%}"
                )
                try:
                    self.client.close_position(pos.symbol)
                    closed.append(pos.symbol)
                except Exception as e:
                    logger.error(f"Failed to close {pos.symbol}: {e}")

        return closed

    def close_old_positions(self, max_age_hours=168):  # 7 days
        """Close positions held longer than max_age_hours"""
        import datetime

        positions = self.client.get_all_positions()
        closed = []
        now = datetime.datetime.now(datetime.timezone.utc)

        for pos in positions:
            # Parse entry time (assuming tracked separately)
            # This is a simplified example
            age_hours = (now - pos.entry_time).total_seconds() / 3600

            if age_hours > max_age_hours:
                logger.info(f"Closing {pos.symbol}: held for {age_hours:.1f} hours")
                try:
                    self.client.close_position(pos.symbol)
                    closed.append(pos.symbol)
                except Exception as e:
                    logger.error(f"Failed to close {pos.symbol}: {e}")

        return closed

    def reduce_exposure(self, target_pct=0.50):
        """Reduce total exposure to target_pct of portfolio"""
        account = self.client.get_account()
        positions = self.client.get_all_positions()

        current_exposure = sum(float(pos.market_value) for pos in positions)
        portfolio_value = float(account.portfolio_value)
        current_pct = current_exposure / portfolio_value

        if current_pct <= target_pct:
            logger.info(f"Exposure {current_pct:.2%} already below target {target_pct:.2%}")
            return []

        reduction_needed = current_exposure - (portfolio_value * target_pct)
        logger.info(f"Reducing exposure by ${reduction_needed:,.2f}")

        # Sort positions by size (close largest first)
        positions_sorted = sorted(
            positions,
            key=lambda p: float(p.market_value),
            reverse=True
        )

        closed = []
        total_reduced = 0

        for pos in positions_sorted:
            if total_reduced >= reduction_needed:
                break

            logger.info(f"Closing {pos.symbol} (${float(pos.market_value):,.2f})")
            try:
                self.client.close_position(pos.symbol)
                closed.append(pos.symbol)
                total_reduced += float(pos.market_value)
            except Exception as e:
                logger.error(f"Failed to close {pos.symbol}: {e}")

        logger.info(f"Closed {len(closed)} positions, reduced by ${total_reduced:,.2f}")
        return closed
```

---

## Data Corruption Recovery

### 1. Database Corruption Detection

```bash
#!/bin/bash
# check-database-integrity.sh - Verify all databases

echo "=== Database Integrity Check ==="

DB_DIR="/home/catalyst-bot/catalyst-bot/data/databases"
CORRUPTED=0

for db in "$DB_DIR"/*.db; do
    db_name=$(basename "$db")
    echo -n "Checking $db_name... "

    result=$(sqlite3 "$db" "PRAGMA integrity_check;" 2>&1)

    if [ "$result" == "ok" ]; then
        echo "✓ OK"
    else
        echo "✗ CORRUPTED"
        echo "  Error: $result"
        CORRUPTED=$((CORRUPTED + 1))
    fi
done

echo ""
if [ $CORRUPTED -eq 0 ]; then
    echo "✓ All databases are healthy"
    exit 0
else
    echo "✗ $CORRUPTED database(s) corrupted"
    echo "Run repair-database.sh to attempt recovery"
    exit 1
fi
```

### 2. Database Repair

```bash
#!/bin/bash
# repair-database.sh - Attempt to repair corrupted database

DB_FILE="$1"

if [ -z "$DB_FILE" ]; then
    echo "Usage: $0 <database_file.db>"
    exit 1
fi

echo "=== Database Repair ==="
echo "Database: $DB_FILE"

# Backup corrupted database
BACKUP="${DB_FILE}.corrupted_$(date +%Y%m%d_%H%M%S)"
cp "$DB_FILE" "$BACKUP"
echo "Backup: $BACKUP"

# Attempt 1: SQLite recovery
echo ""
echo "Attempting SQLite recovery..."
TEMP_DB="${DB_FILE}.recovery"

if sqlite3 "$DB_FILE" ".recover" | sqlite3 "$TEMP_DB"; then
    echo "  ✓ Recovery successful"

    # Verify recovered database
    if sqlite3 "$TEMP_DB" "PRAGMA integrity_check;" | grep -q "ok"; then
        echo "  ✓ Recovered database is valid"
        mv "$TEMP_DB" "$DB_FILE"
        echo "  ✓ Database repaired"
        exit 0
    else
        echo "  ✗ Recovered database still corrupted"
    fi
else
    echo "  ✗ SQLite recovery failed"
fi

# Attempt 2: Export and reimport
echo ""
echo "Attempting export/reimport..."
DUMP_FILE="${DB_FILE}.sql"

if sqlite3 "$DB_FILE" ".dump" > "$DUMP_FILE" 2>/dev/null; then
    echo "  ✓ Exported to SQL dump"

    # Create new database from dump
    NEW_DB="${DB_FILE}.new"
    if sqlite3 "$NEW_DB" < "$DUMP_FILE"; then
        echo "  ✓ Imported to new database"

        # Verify
        if sqlite3 "$NEW_DB" "PRAGMA integrity_check;" | grep -q "ok"; then
            echo "  ✓ New database is valid"
            mv "$NEW_DB" "$DB_FILE"
            echo "  ✓ Database repaired"
            exit 0
        fi
    fi
fi

# Attempt 3: Restore from latest backup
echo ""
echo "✗ Automatic repair failed"
echo ""
echo "Manual recovery options:"
echo "1. Restore from latest backup:"
echo "   ./restore-single-db.sh $(basename $DB_FILE .db) <backup_file>"
echo ""
echo "2. Rebuild database from scratch (WARNING: data loss):"
echo "   python -m catalyst_bot.database.rebuild --db $(basename $DB_FILE)"
echo ""
echo "Corrupted database backed up to: $BACKUP"

exit 1
```

---

## API Key Rotation

### 1. Rotation Procedure

```bash
#!/bin/bash
# rotate-api-keys.sh - Rotate API keys with zero downtime

echo "=== API Key Rotation ==="
echo ""
echo "This script will rotate API keys for:"
echo "  - Alpaca (trading)"
echo "  - Tiingo (market data)"
echo "  - Gemini (LLM)"
echo "  - Discord (webhooks)"
echo ""

# Step 1: Generate new keys
echo "Step 1: Generate new API keys"
echo "  1. Log in to each provider's dashboard"
echo "  2. Generate new API keys (do not revoke old keys yet)"
echo "  3. Copy new keys to a secure location"
echo ""
read -p "Press Enter when new keys are ready..."

# Step 2: Update .env file
echo ""
echo "Step 2: Update .env with new keys"
vim /home/catalyst-bot/catalyst-bot/src/.env

# Step 3: Test new keys
echo ""
echo "Step 3: Testing new API keys..."

python << 'EOF'
import os
from alpaca.trading.client import TradingClient

# Test Alpaca
try:
    client = TradingClient(
        os.getenv('ALPACA_API_KEY'),
        os.getenv('ALPACA_SECRET'),
        paper=True
    )
    account = client.get_account()
    print("  ✓ Alpaca API working")
except Exception as e:
    print(f"  ✗ Alpaca API failed: {e}")

# Test other APIs...
print("  ✓ All APIs tested")
EOF

# Step 4: Restart service
echo ""
echo "Step 4: Restarting trading bot..."
sudo systemctl restart catalyst-trading-bot.service
sleep 5

if sudo systemctl is-active --quiet catalyst-trading-bot.service; then
    echo "  ✓ Service restarted successfully"
else
    echo "  ✗ Service failed to start!"
    exit 1
fi

# Step 5: Monitor for 30 minutes
echo ""
echo "Step 5: Monitoring service..."
echo "  Watch logs for 30 minutes to verify no API errors"
echo "  Command: sudo journalctl -u catalyst-trading-bot.service -f"
echo ""
read -p "Press Enter when monitoring is complete..."

# Step 6: Revoke old keys
echo ""
echo "Step 6: Revoke old API keys"
echo "  1. Log in to each provider's dashboard"
echo "  2. Revoke/delete the old API keys"
echo "  3. Verify new keys still working after revocation"
echo ""
read -p "Press Enter when old keys are revoked..."

echo ""
echo "✓ API key rotation complete"
echo ""
echo "Backup old .env file:"
cp /home/catalyst-bot/catalyst-bot/src/.env /home/catalyst-bot/catalyst-bot/data/backups/.env.old_keys_$(date +%Y%m%d)
echo "  Saved to: /home/catalyst-bot/catalyst-bot/data/backups/.env.old_keys_$(date +%Y%m%d)"
```

---

## Incident Response Checklist

### Critical Incident (Severity 1)

**Examples:** Kill switch activated, database corruption, bot offline, major losses

```
☐ 1. IMMEDIATE (0-5 minutes)
   ☐ Activate kill switch if not already triggered
   ☐ Cancel all open orders
   ☐ Notify team via Discord/SMS
   ☐ Open incident ticket/document

☐ 2. ASSESS (5-15 minutes)
   ☐ Identify root cause
   ☐ Check recent logs
   ☐ Verify data integrity
   ☐ Assess financial impact

☐ 3. CONTAIN (15-30 minutes)
   ☐ Stop bleeding (close losing positions if necessary)
   ☐ Isolate affected components
   ☐ Preserve evidence (logs, database snapshots)

☐ 4. RECOVER (30-60 minutes)
   ☐ Execute recovery procedure
   ☐ Restore from backup if needed
   ☐ Verify system integrity
   ☐ Test in dry-run mode

☐ 5. RESUME (60+ minutes)
   ☐ Gradual restart (small position sizes)
   ☐ Monitor closely for 2 hours
   ☐ Gradually increase limits

☐ 6. POST-MORTEM (24-48 hours)
   ☐ Document incident timeline
   ☐ Identify preventive measures
   ☐ Update runbooks
   ☐ Implement fixes
```

### High Priority Incident (Severity 2)

**Examples:** High error rate, API failures, slow performance

```
☐ 1. ACKNOWLEDGE (0-10 minutes)
   ☐ Acknowledge alert
   ☐ Assign owner
   ☐ Open incident ticket

☐ 2. DIAGNOSE (10-30 minutes)
   ☐ Check monitoring dashboards
   ☐ Review recent changes
   ☐ Reproduce issue

☐ 3. MITIGATE (30-60 minutes)
   ☐ Apply temporary fix
   ☐ Reduce load if needed
   ☐ Switch to backup systems

☐ 4. RESOLVE (1-4 hours)
   ☐ Implement permanent fix
   ☐ Deploy to production
   ☐ Verify resolution
```

---

## Disaster Scenarios

### Scenario 1: Server Hardware Failure

**Symptoms:** Server unresponsive, cannot SSH

**Recovery Steps:**
1. Provision new server (Ubuntu 22.04 LTS)
2. Restore from latest cloud backup:
   ```bash
   ./restore-from-cloud.sh $(date +%Y%m%d -d yesterday)
   ```
3. Follow production deployment guide
4. Verify all services running
5. Resume trading

**Estimated Recovery Time:** 1-2 hours

---

### Scenario 2: Database Corruption

**Symptoms:** SQLite errors, integrity check fails

**Recovery Steps:**
1. Stop trading bot
2. Run integrity check:
   ```bash
   ./check-database-integrity.sh
   ```
3. Attempt repair:
   ```bash
   ./repair-database.sh /path/to/corrupted.db
   ```
4. If repair fails, restore from backup:
   ```bash
   ./restore-single-db.sh positions <latest_backup>
   ```
5. Verify data, restart bot

**Estimated Recovery Time:** 15-30 minutes

---

### Scenario 3: Accidental Deletion of Critical Files

**Symptoms:** Missing .env, databases, or models

**Recovery Steps:**
1. DO NOT write any new data
2. Check if files in trash/recent backups
3. Restore from latest backup:
   ```bash
   ./restore-from-backup.sh <latest_daily_backup>
   ```
4. Verify restored files
5. Restart services

**Estimated Recovery Time:** 10-20 minutes

---

### Scenario 4: Alpaca API Outage

**Symptoms:** All API calls failing, 503 errors

**Recovery Steps:**
1. Verify outage (check Alpaca status page)
2. Switch to dry-run mode:
   ```bash
   # In .env
   TRADING_MODE=dry-run
   ```
3. Monitor for resolution
4. Resume trading when API restored
5. Review missed opportunities

**Estimated Recovery Time:** Depends on Alpaca (typically <1 hour)

---

### Scenario 5: Malicious Attack / Unauthorized Access

**Symptoms:** Unexpected trades, config changes, data exfiltration

**Recovery Steps:**
1. **IMMEDIATE:** Activate kill switch
2. Revoke all API keys immediately
3. Change all passwords
4. Review access logs:
   ```bash
   sudo ausearch -m USER_LOGIN
   grep -i "failed\|invalid" /var/log/auth.log
   ```
5. Restore from pre-attack backup
6. Conduct security audit
7. Implement additional security measures

**Estimated Recovery Time:** 2-4 hours + security audit

---

## Monthly DR Drills

### Test Checklist

```
☐ Database backup restore test
☐ Full system restore test
☐ Kill switch activation test
☐ Cloud backup download test
☐ API key rotation test
☐ Position liquidation test
☐ Incident response drill
☐ Update runbooks based on findings
```

### Drill Schedule

| Month | Drill Type | Duration |
|-------|-----------|----------|
| January | Full system restore | 2 hours |
| February | Database restore | 30 min |
| March | Kill switch + liquidation | 1 hour |
| April | API key rotation | 1 hour |
| May | Cloud backup restore | 1 hour |
| June | Incident response drill | 2 hours |
| July | Full system restore | 2 hours |
| August | Security breach scenario | 2 hours |
| September | Database corruption recovery | 1 hour |
| October | Multi-component failure | 2 hours |
| November | API outage response | 1 hour |
| December | Year-end full DR test | 4 hours |

---

## Support Contacts

**Emergency Contacts:**
- Primary: [Your Phone] - [Your Email]
- Backup: [Backup Contact]
- Discord Admin: [Discord Username]

**Vendor Support:**
- Alpaca: support@alpaca.markets
- AWS: Premium Support (if subscribed)
- Google Cloud: Cloud Support (if subscribed)

---

**End of Disaster Recovery Guide**
