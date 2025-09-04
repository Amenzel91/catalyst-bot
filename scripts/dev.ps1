<#
.SYNOPSIS
  Catalyst-bot developer helpers (PowerShell-native).

.DESCRIPTION
  Functions for env setup, running once/loop, webhook tests, gates, and quick title_ticker smoke tests.
  Source this file in a session:  . .\scripts\dev.ps1
  Requires: Windows PowerShell 5+ or PowerShell 7+, Python venv activated.

.NOTES
  Defaults assume:
    - Main Discord webhook: $env:DISCORD_WEBHOOK_URL
    - Admin/dev webhook:    $env:DISCORD_ADMIN_WEBHOOK (optional)
    - DOTENV_FILE:          .env.staging (recommended for testing)
#>

function Set-CatalystEnv {
  [CmdletBinding()]
  param(
    [string]$Dotenv = ".env.staging",
    [ValidateSet('0','1')][string]$Heartbeat = '1',
    [ValidateSet('0','1')][string]$RecordOnly = '0'
  )
  $env:DOTENV_FILE = $Dotenv
  $env:FEATURE_HEARTBEAT = $Heartbeat
  $env:FEATURE_RECORD_ONLY = $RecordOnly
  Write-Host "DOTENV_FILE=$($env:DOTENV_FILE)  FEATURE_HEARTBEAT=$($env:FEATURE_HEARTBEAT)  FEATURE_RECORD_ONLY=$($env:FEATURE_RECORD_ONLY)"
}

function Start-CatalystOnce {
  [CmdletBinding()]
  param(
    [string]$Dotenv = $env:DOTENV_FILE,
    [string]$SkipSources,
    [string]$MinScore,
    [string]$MinSentAbs
  )
  if ($Dotenv) { $env:DOTENV_FILE = $Dotenv }
  if ($PSBoundParameters.ContainsKey('SkipSources')) { $env:SKIP_SOURCES = $SkipSources }
  if ($PSBoundParameters.ContainsKey('MinScore')) { $env:MIN_SCORE = $MinScore }
  if ($PSBoundParameters.ContainsKey('MinSentAbs')) { $env:MIN_SENT_ABS = $MinSentAbs }

  python -m catalyst_bot.runner --once
}

function Start-CatalystLoop {
  [CmdletBinding()]
  param(
    [string]$Dotenv = $env:DOTENV_FILE,
    [int]$SleepSeconds = 30
  )
  if ($Dotenv) { $env:DOTENV_FILE = $Dotenv }
  python -m catalyst_bot.runner --loop --sleep $SleepSeconds
}

function Test-DiscordWebhook {
  [CmdletBinding()]
  param(
    [switch]$Admin,
    [string]$Webhook, # override both envs if set
    [string]$Message = "ping from Test-DiscordWebhook"
  )
  $hook = if ($Webhook) { $Webhook } elseif ($Admin) { $env:DISCORD_ADMIN_WEBHOOK } else { $env:DISCORD_WEBHOOK_URL }
  if (-not $hook) { throw "No webhook available. Set DISCORD_WEBHOOK_URL or DISCORD_ADMIN_WEBHOOK." }

  $body = @{ content = $Message } | ConvertTo-Json
  try {
    $resp = Invoke-RestMethod -Method Post -Uri $hook -Body $body -ContentType "application/json"
    Write-Host "POST ok (Discord usually returns 204 No Content)."
  } catch {
    Write-Warning ("Webhook POST failed: {0}" -f $_.Exception.Message)
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      Write-Warning ("HTTP status: {0}" -f [int]$_.Exception.Response.StatusCode)
    }
  }
}

function Show-CatalystEnv {
  [CmdletBinding()]
  param()
  Write-Host "DOTENV_FILE=$($env:DOTENV_FILE)"
  Write-Host "DISCORD_WEBHOOK_URL set? " -NoNewline; Write-Host ([bool]$env:DISCORD_WEBHOOK_URL)
  Write-Host "DISCORD_ADMIN_WEBHOOK set? " -NoNewline; Write-Host ([bool]$env:DISCORD_ADMIN_WEBHOOK)
  Write-Host "FEATURE_HEARTBEAT=$($env:FEATURE_HEARTBEAT)  FEATURE_RECORD_ONLY=$($env:FEATURE_RECORD_ONLY)"
  Write-Host "SKIP_SOURCES=$($env:SKIP_SOURCES)  MIN_SCORE=$($env:MIN_SCORE)  MIN_SENT_ABS=$($env:MIN_SENT_ABS)"
  Write-Host "ALLOW_OTC_TICKERS=$($env:ALLOW_OTC_TICKERS)  DOLLAR_TICKERS_REQUIRE_EXCHANGE=$($env:DOLLAR_TICKERS_REQUIRE_EXCHANGE)"
}

function Clear-CatalystGates {
  [CmdletBinding()]
  param()
  Remove-Item Env:\MIN_SCORE -ErrorAction SilentlyContinue
  Remove-Item Env:\MIN_SENT_ABS -ErrorAction SilentlyContinue
  Remove-Item Env:\SKIP_SOURCES -ErrorAction SilentlyContinue
  Write-Host "Cleared MIN_SCORE, MIN_SENT_ABS, SKIP_SOURCES."
}

function Run-TitleTickerSmoke {
  [CmdletBinding()]
  param(
    [string]$Sample = "Alpha (Nasdaq: ABCD) + `$EFGH; OTCMKTS: XYZ should be ignored"
  )
  $code = @"
from catalyst_bot.title_ticker import extract_tickers_from_title as X
s = r'''$Sample'''
print("INPUT  ->", s)
print("OUTPUT ->", X(s))
"@
  $code | python -
}

function New-CatalystEnvFile {
  [CmdletBinding()]
  param(
    [string]$Path = ".env.staging",
    [string]$MainWebhook = "",
    [string]$AdminWebhook = "",
    [string]$FinvizAuthToken = ""
  )

  $content = @"
# ===== Catalyst-bot (.env.staging) =====
# Discord webhooks
DISCORD_WEBHOOK_URL=$MainWebhook
DISCORD_ADMIN_WEBHOOK=$AdminWebhook

# Behavior flags
FEATURE_HEARTBEAT=1
FEATURE_RECORD_ONLY=0

# Feeds / auth
FINVIZ_AUTH_TOKEN=$FinvizAuthToken

# Analyzer schedule (UTC, HH:MM 24h) — optional
ANALYZER_RUN_UTC=13:00

# Classifier gates (optional)
MIN_SCORE=
MIN_SENT_ABS=
CATEGORIES_ALLOW=

# Source-level skip CSV (optional)
SKIP_SOURCES=

# Price ceiling (drop items with last_price > value)
PRICE_CEILING=

# Title ticker extraction toggles
ALLOW_OTC_TICKERS=
DOLLAR_TICKERS_REQUIRE_EXCHANGE=
"@

  Set-Content -Path $Path -Value $content -Encoding UTF8 -NoNewline
  Write-Host "Wrote $Path"
}
