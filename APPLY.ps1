param(
    [Parameter(Mandatory=$true)]
    [string]$RepoPath
)

Write-Host "Applying illiquid ticker filtering patch..."


# Copy documentation and env example updates
Copy-Item -Path "$PSScriptRoot/CHANGELOG.md" -Destination (Join-Path $RepoPath 'CHANGELOG.md') -Force
Copy-Item -Path "$PSScriptRoot/MIGRATIONS.md" -Destination (Join-Path $RepoPath 'MIGRATIONS.md') -Force
Copy-Item -Path "$PSScriptRoot/env.example.ini" -Destination (Join-Path $RepoPath 'env.example.ini') -Force

# -----------------------------------------------------------------------
# Modify config.py to add a price_floor property if missing.  We search for
# the definition of sentiment_weight_earnings and insert a new line
# afterwards.  This avoids having to ship the entire config file in the
# patch.  The operation is idempotent: if the property is already
# present, no changes are made.
$configPath = Join-Path $RepoPath 'src\catalyst_bot\config.py'
if (Test-Path $configPath) {
    $content = Get-Content -Raw -LiteralPath $configPath
    if ($content -notmatch 'price_floor') {
        $pattern = 'sentiment_weight_earnings.*?\n'
        $replacement = "$&    # --- Liquidity filtering ---\n    price_floor: float = float(os.getenv(\"PRICE_FLOOR\", \"0\") or \"0\")\n"
        $updated = [regex]::Replace($content, $pattern, $replacement, 1)
        Set-Content -LiteralPath $configPath -Value $updated -Encoding UTF8
    }
}

# -----------------------------------------------------------------------
# Modify feeds.py to read PRICE_FLOOR and apply the skip logic.  We
# insert a new parsing block after the PRICE_CEILING assignment and
# inject a skip condition inside the all_items loop.  These edits are
# performed only if PRICE_FLOOR is not referenced already.
$feedsPath = Join-Path $RepoPath 'src\catalyst_bot\feeds.py'
if (Test-Path $feedsPath) {
    $content = Get-Content -Raw -LiteralPath $feedsPath
    if ($content -notmatch 'price_floor') {
        # Add parsing of PRICE_FLOOR after price_ceiling definition
        $content = $content -replace '(price_ceiling\s*=\s*float\([^\n]+\)\s*\n)', "$1    try:\n        price_floor = float(os.getenv(\"PRICE_FLOOR\", \"0\").strip() or \"0\")\n    except Exception:\n        price_floor = 0.0\n"
        # Insert gating inside the loop over all_items.  We look for the
        # start of the loop ('for item in all_items') and insert logic
        # immediately after retrieving the ticker.
        $patternLoop = 'for item in all_items:\n\s+ticker = item.get\("ticker"\)'
        $replacementLoop = "for item in all_items:`n        ticker = item.get(\"ticker\")`n        # Skip illiquid penny stocks when price_floor is set`n        if (ticker -and price_floor -gt 0):`n            tick = ticker.strip().upper()`n            try:`n                last_price, _ = market.get_last_price_snapshot(tick)`n            except:`n                last_price = None`n            if (last_price -ne $null -and last_price -lt price_floor):`n                continue`n"
        $content = [regex]::Replace($content, $patternLoop, $replacementLoop, 1)
        Set-Content -LiteralPath $feedsPath -Value $content -Encoding UTF8
    }
}

Write-Host "Patch applied successfully."

# Clean up any stray patch files (the src directory in the patch is unused
# since modifications are applied via in-place edits).  Remove the
# directory under the patch to avoid confusion.  Note: this does not
# affect the repository; it only cleans up the extracted patch folder.
$patchSrc = Join-Path $PSScriptRoot 'src'
if (Test-Path $patchSrc) {
    Remove-Item -Path $patchSrc -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Patch applied successfully."