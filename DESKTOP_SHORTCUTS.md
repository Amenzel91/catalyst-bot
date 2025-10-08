# 🖱️ Desktop Shortcuts Setup Guide

**Quick Access to Catalyst-Bot Launchers**

This guide shows you how to create Windows desktop shortcuts for easy one-click launching of the bot and its components.

---

## 📂 Available Launchers

You have 7 launcher scripts in the bot directory:

| Launcher | Purpose | Usage |
|----------|---------|-------|
| **start_all.bat** | 🚀 **RECOMMENDED** - Starts everything | Production use |
| **start_tunnel.bat** | Shows Discord interaction URL | Setup / URL changed |
| **start_bot_once.bat** | Single test cycle | Testing changes |
| **start_bot_loop.bat** | Continuous production loop | Main bot only |
| **start_ollama.bat** | Mistral LLM server | Required for sentiment |
| **start_interaction_server.bat** | Discord button handler | Required for interactions |
| **start_quickchart.bat** | Chart generation (Docker) | Optional, enhances charts |

---

## 🎯 Recommended Setup (2 Shortcuts)

### Option A: Full Automation (Best for Daily Use)

**Create 1 shortcut:**
- **start_all.bat** - Launches everything in order with prompts

### Option B: Modular Control (Best for Development)

**Create 2 shortcuts:**
1. **start_tunnel.bat** - Get Discord URL when needed
2. **start_bot_loop.bat** - Run the main bot

---

## 📝 How to Create Desktop Shortcuts

### Method 1: Right-Click Drag (Easiest)

1. Open File Explorer
2. Navigate to: `C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot`
3. **Right-click** on `start_all.bat` and **drag** it to your Desktop
4. Release and select **"Create shortcuts here"**
5. Rename the shortcut to something friendly like **"🚀 Catalyst Bot"**

### Method 2: Send To Desktop (Classic)

1. Navigate to the bot folder
2. **Right-click** on `start_all.bat`
3. Select **Send to** > **Desktop (create shortcut)**
4. Rename the shortcut on your Desktop

### Method 3: PowerShell Script (Automated)

Run this PowerShell command to create all shortcuts automatically:

```powershell
# Run this in PowerShell (Run as Administrator)
cd "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"

# Create Desktop shortcuts
$WshShell = New-Object -comObject WScript.Shell
$Desktop = [System.Environment]::GetFolderPath('Desktop')

# Main launcher
$Shortcut = $WshShell.CreateShortcut("$Desktop\🚀 Catalyst Bot - Start All.lnk")
$Shortcut.TargetPath = "$PWD\start_all.bat"
$Shortcut.WorkingDirectory = "$PWD"
$Shortcut.Description = "Start all Catalyst-Bot services (Ollama, QuickChart, Tunnel, Bot)"
$Shortcut.Save()

# Tunnel (for Discord URL)
$Shortcut = $WshShell.CreateShortcut("$Desktop\🌐 Catalyst Bot - Discord URL.lnk")
$Shortcut.TargetPath = "$PWD\start_tunnel.bat"
$Shortcut.WorkingDirectory = "$PWD"
$Shortcut.Description = "Get Discord Interaction Endpoint URL"
$Shortcut.Save()

# Test mode
$Shortcut = $WshShell.CreateShortcut("$Desktop\🧪 Catalyst Bot - Test Once.lnk")
$Shortcut.TargetPath = "$PWD\start_bot_once.bat"
$Shortcut.WorkingDirectory = "$PWD"
$Shortcut.Description = "Run single bot cycle for testing"
$Shortcut.Save()

Write-Host "✅ Desktop shortcuts created!" -ForegroundColor Green
```

---

## 🎨 Customizing Shortcut Icons (Optional)

### Change Icon to Something Cooler

1. **Right-click** your desktop shortcut
2. Select **Properties**
3. Click **Change Icon...**
4. Browse to Windows icon library: `C:\Windows\System32\shell32.dll`
5. Pick an icon (recommended: rocket 🚀, chart 📊, or gear ⚙️)
6. Click **OK** > **Apply**

### Popular Icon Choices

- **Rocket** - Index 137 in shell32.dll (for start_all.bat)
- **Network** - Index 14 (for start_tunnel.bat)
- **Gear** - Index 71 (for start_bot_loop.bat)

---

## 🚀 Usage Workflow

### First Time Setup

1. **Double-click** `🌐 Catalyst Bot - Discord URL` shortcut
2. Copy the `https://XXXXX.trycloudflare.com` URL
3. Go to [Discord Developer Portal](https://discord.com/developers/applications)
4. Your App > **General Information** > **Interactions Endpoint URL**
5. Paste the URL and **Save Changes**

### Daily Production Use

1. **Double-click** `🚀 Catalyst Bot - Start All` shortcut
2. Wait for services to start (windows will open)
3. When prompted, verify Discord URL is still valid (if tunnel restarted)
4. Bot will start running in the main window
5. Monitor logs and alerts

### Testing Changes

1. **Double-click** `🧪 Catalyst Bot - Test Once` shortcut
2. Bot runs ONE cycle and shows results
3. Check logs for errors
4. If all good, use the full launcher

---

## 🛠️ Troubleshooting

### Shortcut Opens Then Closes Immediately

**Cause:** Batch file encountered an error
**Fix:** Edit the `.bat` file and ensure paths are correct

### "Command Not Found" Errors

**Cause:** Required software not installed or not in PATH
**Fixes:**
- **Ollama:** Download from https://ollama.ai/download
- **Docker:** Download from https://docker.com/get-started
- **Cloudflared:** Already downloaded, or run:
  ```bash
  curl -L -o cloudflare-tunnel-windows-amd64.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  ```

### Tunnel URL Changes Every Restart

**Expected Behavior:** Cloudflare free tunnels get random URLs
**Solutions:**
- **Option 1:** Use a Named Tunnel (requires Cloudflare account)
- **Option 2:** Update Discord URL each restart (takes 30 seconds)
- **Option 3:** Run bot as Windows Service (NSSM) so tunnel stays persistent

---

## 🎯 Pro Tips

### Pin to Taskbar (Even Better Than Desktop)

1. Create desktop shortcut
2. **Right-click** shortcut
3. Select **Pin to taskbar**
4. Now it's always one click away!

### Run at Startup (Auto-Launch on Boot)

1. Press **Win + R**
2. Type: `shell:startup`
3. Copy your shortcut into the Startup folder
4. Bot will auto-start when Windows boots

### Create a "Bot Control Panel" Folder

1. Create folder: `C:\BotLaunchers\`
2. Move all `.bat` files there
3. Create shortcuts from that folder
4. Cleaner organization!

---

## 📋 Quick Reference

### Main Shortcuts You Actually Need

```
🚀 Catalyst Bot - Start All.lnk
   └─ Double-click this every day to start production

🌐 Catalyst Bot - Discord URL.lnk
   └─ Only needed when Discord URL expires

🧪 Catalyst Bot - Test Once.lnk
   └─ Use before deploying changes
```

---

## 🔗 Related Files

- **STARTUP_CHECKLIST.md** - Pre-flight checks before starting bot
- **DEPLOYMENT_CHECKLIST.md** - Production deployment guide
- **PERFORMANCE_FIX_PLAN.md** - Performance optimization settings

---

**You're all set! 🎉**

Now you can launch your bot with a single click instead of typing commands.
