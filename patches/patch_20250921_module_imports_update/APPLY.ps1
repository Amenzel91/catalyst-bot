param(
    [Parameter(Mandatory=$true)]
    [string]$RepoRoot,
    [Parameter(Mandatory=$true)]
    [string]$PatchRoot
)

<#
This script applies the module import fixes for the catalyst bot.  It copies the updated ``__init__.py``
files from the patch into both the canonical package under ``catalyst-bot-main/src/catalyst_bot`` and the
root-level package under ``src/catalyst_bot``.  If the root-level package is missing, it will be created
by copying the entire canonical package into ``src/catalyst_bot``.  The script is idempotent: running it
multiple times will not duplicate work.
#>

$ErrorActionPreference = 'Stop'

function Copy-IfChanged {
    param(
        [string]$SourceFile,
        [string]$DestinationFile
    )
    if (-not (Test-Path $SourceFile)) {
        throw "Source file not found: $SourceFile"
    }
    $destDir = Split-Path $DestinationFile -Parent
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }
    $shouldCopy = $true
    if (Test-Path $DestinationFile) {
        $srcHash = (Get-FileHash -Algorithm SHA256 -Path $SourceFile).Hash
        $dstHash = (Get-FileHash -Algorithm SHA256 -Path $DestinationFile).Hash
        if ($srcHash -eq $dstHash) {
            $shouldCopy = $false
        }
    }
    if ($shouldCopy) {
        Copy-Item -Force $SourceFile $DestinationFile
        Write-Host "Updated $DestinationFile"
    }
}

# Normalise paths
$RepoRoot = (Resolve-Path $RepoRoot).Path
$PatchRoot = (Resolve-Path $PatchRoot).Path

# Paths to the updated __init__.py files in the patch
$srcInit    = Join-Path $PatchRoot 'src' 'catalyst_bot' '__init__.py'
$canonInit  = Join-Path $PatchRoot 'catalyst-bot' 'catalyst-bot-main' 'src' 'catalyst_bot' '__init__.py'

# Copy __init__.py into canonical package
$destCanon  = Join-Path $RepoRoot 'catalyst-bot' 'catalyst-bot-main' 'src' 'catalyst_bot' '__init__.py'
Copy-IfChanged -SourceFile $canonInit -DestinationFile $destCanon

# Ensure root-level package exists and synchronise
$rootSrc = Join-Path $RepoRoot 'src'
if (-not (Test-Path (Join-Path $rootSrc 'catalyst_bot'))) {
    # copy entire canonical package
    $canonicalPkg = Join-Path $RepoRoot 'catalyst-bot' 'catalyst-bot-main' 'src' 'catalyst_bot'
    if (-not (Test-Path $canonicalPkg)) {
        throw "Canonical package path '$canonicalPkg' does not exist."
    }
    Copy-Item -Recurse -Force $canonicalPkg (Join-Path $rootSrc 'catalyst_bot')
    Write-Host "Root-level package synchronised."
}

# Copy updated __init__.py into root-level package
$destRoot = Join-Path $RepoRoot 'src' 'catalyst_bot' '__init__.py'
Copy-IfChanged -SourceFile $srcInit -DestinationFile $destRoot

Write-Host "catalyst_bot __init__.py files updated."