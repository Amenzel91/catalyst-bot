param(
    [Parameter(Mandatory=$true)][string]$RepoPath
)

# APPLY.ps1 - Overlay the SEC summarisation and QuickChart URL patch
#
# This script copies modified files from the patch directory into
# the target repository.  Run this script from the patch root with
# the `-RepoPath` argument pointing to your cloned catalyst-bot repo.

$ErrorActionPreference = 'Stop'

function Copy-File {
    param(
        [string]$Source,
        [string]$Destination
    )
    $destDir = Split-Path $Destination
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -Path $Source -Destination $Destination -Force
}

# Root of this patch (the directory containing APPLY.ps1)
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Copy modified Python modules
Copy-File "$PatchRoot/src/catalyst_bot/sec_digester.py" "$RepoPath/src/catalyst_bot/sec_digester.py"
Copy-File "$PatchRoot/src/catalyst_bot/feeds.py" "$RepoPath/src/catalyst_bot/feeds.py"
Copy-File "$PatchRoot/src/catalyst_bot/config.py" "$RepoPath/src/catalyst_bot/config.py"
Copy-File "$PatchRoot/src/catalyst_bot/charts.py" "$RepoPath/src/catalyst_bot/charts.py"

# Copy environment example and docs
Copy-File "$PatchRoot/env.example.ini" "$RepoPath/env.example.ini"
Copy-File "$PatchRoot/CHANGELOG.md" "$RepoPath/CHANGELOG.md"
Copy-File "$PatchRoot/MIGRATIONS.md" "$RepoPath/MIGRATIONS.md"

Write-Host "Patch applied successfully."
