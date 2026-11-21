# Run LOCALLY (Windows). Exports the live server code (secret-scanned on the server),
# syncs it into this repo, and shows what changed. Commit and push are done after review:
#   git add -A; git commit -m "..."; git push
$ErrorActionPreference = "Continue"   # workbench writes progress to stderr; rely on exit codes instead
$w = "$env:LOCALAPPDATA\Programs\workbench\workbench.exe"
$i = "i-bp1j8zmdc5qgxbghfsmz"
$repo = Split-Path $PSScriptRoot -Parent
$tmp = Join-Path $env:TEMP "gh-export-$(Get-Random)"
New-Item -ItemType Directory -Force $tmp | Out-Null

$b = [Convert]::ToBase64String([IO.File]::ReadAllBytes("$PSScriptRoot\export-from-server.sh"))
& $w exec -i $i --timeout 300 -c "echo $b | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { throw "export failed or secret scan refused; nothing synced" }
& $w download /tmp/gh-export.tgz "$tmp\" -i $i 2>&1 | Out-Null
if (-not (Test-Path "$tmp\gh-export.tgz")) { throw "download failed; nothing synced" }
& $w exec -i $i --timeout 60 -c "rm -f /tmp/gh-export.tgz" 2>&1 | Out-Null

# replace exported paths; keep repo-only files (README, CHANGES, LICENSE, ops/, .gitignore)
foreach ($p in "app", "scripts", "prompts") { if (Test-Path "$repo\$p") { Remove-Item -Recurse -Force "$repo\$p" } }
tar -xzf "$tmp\gh-export.tgz" -C $repo
Remove-Item -Recurse -Force $tmp
Set-Location $repo
git add -A
git status --short
