param(
  [string]$RepoRoot=".",
  [string]$PatchRoot="."
)
$ErrorActionPreference="Stop"
$RepoRoot  = (Resolve-Path $RepoRoot).Path
$PatchRoot = (Resolve-Path $PatchRoot).Path

function Copy-IfChanged($src, $dst){
  if (-not (Test-Path $dst)){
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -Force $src $dst; Write-Host "Updated $($dst.Substring($RepoRoot.Length+1))"
  } else {
    $srcHash = (Get-FileHash -Algorithm SHA256 -Path $src).Hash
    $dstHash = (Get-FileHash -Algorithm SHA256 -Path $dst).Hash
    if ($srcHash -ne $dstHash){
      Copy-Item -Force $src $dst; Write-Host "Updated $($dst.Substring($RepoRoot.Length+1))"
    }
  }
}
# Copy watchlist.py
Copy-IfChanged "$PatchRoot/src/catalyst_bot/watchlist.py" (Join-Path $RepoRoot "src/catalyst_bot/watchlist.py")
# Copy CHANGELOG.md
Copy-IfChanged "$PatchRoot/CHANGELOG.md" (Join-Path $RepoRoot "CHANGELOG.md")
