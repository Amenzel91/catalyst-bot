# scripts/quick-pull.ps1
param(
  [string]$Branch = "main",
  [switch]$Autostash = $true
)

function Run($cmd) {
  Write-Host "→ $cmd"
  cmd /c $cmd
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $cmd" }
}

# Ensure we’re in a git repo
cmd /c "git rev-parse --is-inside-work-tree" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Not a git repo. Open the project folder first." }

# Optionally stash local changes
$stashed = $false
if ($Autostash) {
  $status = (cmd /c "git status --porcelain")
  if ($status) {
    Run "git stash push -u -m autosync-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    $stashed = $true
  }
}

Run "git fetch --all --prune"
# Rebase keeps history clean; ff-only avoids merge commits
cmd /c "git pull --rebase --autostash origin $Branch"
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Pull failed (likely conflict). Resolve manually in Git/VSCode."
  if ($stashed) { Write-Host "A stash was created. Use 'git stash list' and 'git stash pop' after resolving." }
  exit 1
}

if ($stashed) {
  # If autostash didn’t re-apply, try pop (no-op if empty)
  cmd /c "git stash pop" | Out-Null
}

Write-Host "✅ Up to date."
