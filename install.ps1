# Install Claude Code multi-account profiles on native Windows PowerShell.
# Usage:  pwsh -File install.ps1
# TOOLS = this repo (logic). DATA = account credentials/transcripts, never synced.
$tools = Split-Path -Parent $MyInvocation.MyCommand.Path
$data  = if ($env:CLAUDE_PROFILE_HOME) { $env:CLAUDE_PROFILE_HOME } else { Join-Path $HOME ".claude-profiles" }

if (-not (Get-Command python3, python -ErrorAction SilentlyContinue)) {
    Write-Error "python3 not found. Install from python.org or 'winget install Python.Python.3'"; exit 1
}
New-Item -ItemType Directory -Force -Path $data | Out-Null
$line = "Import-Module `"$tools\shell\ClaudeProfiles.psm1`""
if (-not (Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }
if (Select-String -Path $PROFILE -Pattern "ClaudeProfiles.psm1" -Quiet) {
    Write-Host "  already wired: $PROFILE"
} else {
    Copy-Item $PROFILE "$PROFILE.bak" -Force
    Add-Content $PROFILE "`n# Claude Code multi-account profiles`n$line"
    Write-Host "  added to: $PROFILE  (backup at $PROFILE.bak)"
}
Write-Host "`ntools: $tools`ndata : $data`ndone. restart PowerShell, then:  claude-profiles"
