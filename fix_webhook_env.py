"""
Fix Discord webhook by removing the stale environment variable.
This will let the .env file take precedence.
"""
import os
import sys

# For Windows - remove from registry
if sys.platform == "win32":
    try:
        import winreg

        # Open the user environment variables key
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Environment',
            0,
            winreg.KEY_ALL_ACCESS
        )

        try:
            # Try to delete the DISCORD_WEBHOOK_URL variable
            winreg.DeleteValue(key, 'DISCORD_WEBHOOK_URL')
            print("[SUCCESS] Removed DISCORD_WEBHOOK_URL from Windows environment variables")
            print("           The bot will now use the .env file")
            print("\nPlease restart PowerShell for the change to take effect.")
        except FileNotFoundError:
            print("[INFO] DISCORD_WEBHOOK_URL not found in Windows environment variables")
            print("       (This is fine - .env file will be used)")
        finally:
            winreg.CloseKey(key)

        # Also show current session value
        current = os.getenv('DISCORD_WEBHOOK_URL', '')
        if current:
            print(f"\n[NOTE] Current PowerShell session still has the old value.")
            print(f"       Close and reopen PowerShell, or run:")
            print(f"       Remove-Item Env:\\DISCORD_WEBHOOK_URL")

    except Exception as e:
        print(f"[ERROR] Failed to modify environment variables: {e}")
        print("\nManual fix: Run this in PowerShell as Administrator:")
        print("[System.Environment]::SetEnvironmentVariable('DISCORD_WEBHOOK_URL', $null, 'User')")
        sys.exit(1)
else:
    print("This script is for Windows only.")
    print("On Linux/Mac, edit your ~/.bashrc or ~/.zshrc and remove the DISCORD_WEBHOOK_URL line")
    sys.exit(1)

print("\n" + "="*70)
print("Next steps:")
print("  1. Close this PowerShell window")
print("  2. Open a new PowerShell window")
print("  3. cd to the project directory")
print("  4. Activate venv: .\\.venv\\Scripts\\Activate.ps1")
print("  5. Test: .venv\\Scripts\\python test_discord_alert.py")
print("="*70)
