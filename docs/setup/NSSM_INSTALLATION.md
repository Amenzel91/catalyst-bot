# NSSM (Non-Sucking Service Manager) Installation Guide

This guide explains how to install NSSM for running Catalyst-Bot as a Windows service.

## What is NSSM?

NSSM (Non-Sucking Service Manager) is a service helper for Windows that makes it easy to run any application as a Windows service. It provides:

- Automatic restart on failure
- Start on boot
- Graceful shutdown handling
- Log file management
- No code changes needed

## Installation Methods

### Method 1: Chocolatey (Recommended)

The easiest way to install NSSM is via Chocolatey package manager.

#### Step 1: Install Chocolatey

If you don't have Chocolatey installed:

1. Open PowerShell **as Administrator**
2. Run this command:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

3. Close and reopen PowerShell as Administrator

#### Step 2: Install NSSM

```powershell
choco install nssm -y
```

#### Step 3: Verify Installation

```powershell
nssm --version
```

You should see the NSSM version number.

### Method 2: Manual Installation

If you prefer not to use Chocolatey:

#### Step 1: Download NSSM

1. Go to [https://nssm.cc/download](https://nssm.cc/download)
2. Download the latest release (e.g., `nssm-2.24.zip`)
3. Extract the ZIP file

#### Step 2: Choose the Correct Version

The ZIP contains two folders:
- `win32` - For 32-bit Windows
- `win64` - For 64-bit Windows (most modern systems)

**To check your Windows version:**
- Press `Win + Pause/Break`
- Look for "System type"
- Or run: `systeminfo | findstr /C:"System Type"`

#### Step 3: Copy NSSM to System Directory

1. Navigate to the appropriate folder (`win32` or `win64`)
2. Copy `nssm.exe` to one of these locations:
   - `C:\Windows\System32\` (recommended)
   - Or any folder in your PATH

**Using Command Prompt (as Administrator):**

```cmd
REM For 64-bit Windows
copy path\to\nssm-2.24\win64\nssm.exe C:\Windows\System32\

REM For 32-bit Windows
copy path\to\nssm-2.24\win32\nssm.exe C:\Windows\System32\
```

#### Step 4: Verify Installation

Open a new Command Prompt and run:

```cmd
nssm --version
```

## Using NSSM with Catalyst-Bot

Once NSSM is installed, you can use the provided batch files:

### Install as Service

```cmd
REM Right-click and "Run as Administrator"
install_service.bat
```

This will:
- Check for NSSM
- Configure the service
- Set auto-restart on failure
- Configure logging

### Manage the Service

```cmd
REM Start the service
net start CatalystBot

REM Stop the service
net stop CatalystBot

REM Restart the service
restart_service.bat

REM Check service status
nssm status CatalystBot

REM View service configuration
nssm get CatalystBot *
```

### Uninstall Service

```cmd
REM Right-click and "Run as Administrator"
uninstall_service.bat
```

## NSSM Commands Reference

### Basic Commands

```cmd
REM Install a service
nssm install ServiceName "C:\path\to\program.exe" "arguments"

REM Start a service
nssm start ServiceName

REM Stop a service
nssm stop ServiceName

REM Restart a service
nssm restart ServiceName

REM Remove a service
nssm remove ServiceName confirm

REM Check service status
nssm status ServiceName
```

### Configuration Commands

```cmd
REM Set working directory
nssm set ServiceName AppDirectory "C:\path\to\working\dir"

REM Set environment variable
nssm set ServiceName AppEnvironmentExtra VAR=value

REM Set log file paths
nssm set ServiceName AppStdout "C:\path\to\stdout.log"
nssm set ServiceName AppStderr "C:\path\to\stderr.log"

REM Set restart policy
nssm set ServiceName AppExit Default Restart

REM Set startup type (auto, manual, disabled)
nssm set ServiceName Start SERVICE_AUTO_START

REM Get all parameters
nssm get ServiceName *

REM Get specific parameter
nssm get ServiceName AppDirectory
```

### Advanced Configuration

```cmd
REM Set restart delay (milliseconds)
nssm set ServiceName AppRestartDelay 10000

REM Set throttle (minimum time before restart)
nssm set ServiceName AppThrottle 60000

REM Rotate logs
nssm set ServiceName AppStdoutCreationDisposition 4
nssm set ServiceName AppStderrCreationDisposition 4

REM Set service description
nssm set ServiceName Description "My service description"

REM Set display name
nssm set ServiceName DisplayName "My Service"

REM Set service dependencies
nssm set ServiceName DependOnService Dependency1 Dependency2
```

## Troubleshooting

### Issue: "nssm: command not found"

**Solution:**
- NSSM is not in your PATH
- Reinstall using Chocolatey, or
- Copy `nssm.exe` to `C:\Windows\System32\`

### Issue: "Access denied" when installing service

**Solution:**
- You need administrator privileges
- Right-click Command Prompt or PowerShell
- Select "Run as Administrator"

### Issue: Service won't start

**Check:**
1. Is the path to Python correct?
   ```cmd
   nssm get CatalystBot Application
   ```

2. Does the working directory exist?
   ```cmd
   nssm get CatalystBot AppDirectory
   ```

3. Check service logs:
   ```cmd
   type data\logs\service_stderr.log
   ```

4. Try running manually first:
   ```cmd
   .venv\Scripts\python -m catalyst_bot.runner --loop
   ```

### Issue: Service starts but immediately stops

**Check:**
1. Python path is correct and virtual environment exists
2. `.env` file exists in the working directory
3. No syntax errors in code
4. Check service logs for Python errors

### Issue: Can't uninstall service

**Try:**
1. Stop the service first:
   ```cmd
   net stop CatalystBot
   ```

2. Force remove if needed:
   ```cmd
   sc delete CatalystBot
   ```

## Service Best Practices

### 1. Use Virtual Environments

Always use a virtual environment for Python projects:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Point NSSM to the virtual environment's Python:
```cmd
nssm set CatalystBot Application "C:\path\to\project\.venv\Scripts\python.exe"
```

### 2. Configure Logging

Always set up logging to capture issues:

```cmd
nssm set CatalystBot AppStdout "C:\path\to\logs\stdout.log"
nssm set CatalystBot AppStderr "C:\path\to\logs\stderr.log"
```

Enable log rotation:
```cmd
nssm set CatalystBot AppStdoutCreationDisposition 4
nssm set CatalystBot AppStderrCreationDisposition 4
```

### 3. Set Restart Policies

Configure automatic restart on failure:

```cmd
nssm set CatalystBot AppExit Default Restart
nssm set CatalystBot AppRestartDelay 10000
nssm set CatalystBot AppThrottle 60000
```

This will:
- Restart on any exit code
- Wait 10 seconds before restarting
- Throttle restarts if failing too frequently

### 4. Set Startup Type

For production:
```cmd
nssm set CatalystBot Start SERVICE_AUTO_START
```

For development:
```cmd
nssm set CatalystBot Start SERVICE_DEMAND_START
```

### 5. Document Configuration

Save your service configuration:

```cmd
nssm get CatalystBot * > service_config.txt
```

## Alternatives to NSSM

If you prefer not to use NSSM, consider:

1. **Task Scheduler**
   - Built into Windows
   - Can run on startup
   - Less flexible than NSSM

2. **Windows Service (native)**
   - Requires code changes
   - More complex setup
   - Better integration with Windows

3. **Docker**
   - Modern containerized approach
   - Better isolation
   - Requires Docker Desktop

4. **Manual with `pythonw`**
   - Run in background without console
   - No auto-restart
   - Not recommended for production

## References

- **NSSM Official Site**: [https://nssm.cc/](https://nssm.cc/)
- **NSSM Usage**: [https://nssm.cc/usage](https://nssm.cc/usage)
- **Chocolatey**: [https://chocolatey.org/](https://chocolatey.org/)
- **Windows Services**: [https://docs.microsoft.com/en-us/windows/win32/services/services](https://docs.microsoft.com/en-us/windows/win32/services/services)

---

**WAVE 2.3: 24/7 Deployment Infrastructure**
