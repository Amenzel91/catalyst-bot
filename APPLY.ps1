# Apply patch script
# Copies modified files into the target repo directory
param(
    [string]$RepoPath
)
$ErrorActionPreference = 'Stop'
if (-not $RepoPath) { Write-Host 'Usage: APPLY.ps1 -RepoPath <repo-root>'; exit 1 }

Copy-Item -Path "$PSScriptRoot\src\catalyst_bot\charts.py" -Destination "$RepoPath\src\catalyst_bot\charts.py" -Force
Copy-Item -Path "$PSScriptRoot\CHANGELOG.md" -Destination "$RepoPath\CHANGELOG.md" -Force
Write-Host 'Patch applied successfully.'
