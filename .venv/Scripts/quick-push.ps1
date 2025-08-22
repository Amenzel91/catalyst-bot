# scripts/quick-push.ps1
param(
  [string]$Branch = "main"
)

function Run($cmd) {
  Write-Host "→ $cmd"
  cmd /c $cmd
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $cmd" }
}

cmd /c "git rev-parse --is-inside-work-tree" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Not a git repo. Open the project folder first." }

# Always rebase on remote first (avoid merge commits)
cmd /c "git pull --rebase --autostash origin $Branch"
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Pull/rebase failed (conflict?). Resolve manually, then re-run."
  exit 1
}

# Stage & commit only if there are changes
$changes = (cmd /c "git status --porcelain")
if (-not $changes) {
  Write-Host "No local changes to commit. Pushing anyway to sync tracking branch…"
} else {
  Run "git add -A"
  $msg = "chore(sync): $(hostname) $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
  cmd /c "git commit -m `"$msg`""
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Nothing to commit (maybe whitespace only)."
  }
}

Run "git push -u origin $Branch"
Write-Host "✅ Pushed to $Branch."
