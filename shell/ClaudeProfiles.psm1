# Claude Code multi-account profiles - native Windows PowerShell
# Install:  see install.ps1  (or dot-source from $PROFILE)
$script:ProfileHome = if ($env:CLAUDE_PROFILE_HOME) { $env:CLAUDE_PROFILE_HOME }
                      else { Join-Path $HOME ".claude-profiles" }
$script:Py  = (Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$script:ToolsDir = Split-Path -Parent $PSScriptRoot
$script:Core = Join-Path $script:ToolsDir "bin\claude-profiles.py"

function Set-ClaudeProfile {
    [CmdletBinding()] param([Parameter(Position=0)][string]$Name)
    if (-not $Name) {
        $n = if ($env:CLAUDE_PROFILE_NAME) { $env:CLAUDE_PROFILE_NAME } else { "default" }
        $d = if ($env:CLAUDE_CONFIG_DIR)   { $env:CLAUDE_CONFIG_DIR }   else { Join-Path $HOME ".claude" }
        Write-Host "claude profile: $n"; Write-Host "config dir    : $d"; return
    }
    if ($Name -ne "default" -and ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $Name -match '\.\.')) {
        Write-Error "invalid profile name: $Name"; return
    }
    if ($Name -eq "default") {
        Remove-Item Env:CLAUDE_CONFIG_DIR   -ErrorAction SilentlyContinue
        Remove-Item Env:CLAUDE_PROFILE_NAME -ErrorAction SilentlyContinue
    } else {
        $dir = Join-Path $script:ProfileHome $Name
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $env:CLAUDE_CONFIG_DIR   = $dir
        $env:CLAUDE_PROFILE_NAME = $Name
    }
}

# `claude-profiles` with no subcommand means `status`; a known subcommand goes
# straight through. Keep this list in step with the core - tests/test_core.py
# checks it against the core's own subcommands.
$script:Subcommands = @('clear','clone','best','doctor','handoff','path','prune',
                        'remove','sessions','status','statusline','update')
function Get-ClaudeProfiles {
    if ($args.Count -gt 0 -and $script:Subcommands -contains [string]$args[0]) {
        & $script:Py $script:Core @args
    } else {
        & $script:Py $script:Core status @args
    }
}
function Get-ClaudeSessions { & $script:Py $script:Core sessions @args }
function Move-ClaudeSession { & $script:Py $script:Core handoff  @args }

function Test-ClaudeProfiles  { & $script:Py $script:Core doctor @args }
function Copy-ClaudeProfile   { & $script:Py $script:Core clone  @args }
function Clear-ClaudeSessions { & $script:Py $script:Core prune  @args }
function Remove-ClaudeSessions { & $script:Py $script:Core clear  @args }
function Find-ClaudeProfile   { & $script:Py $script:Core best   @args }
function Update-ClaudeProfiles { & $script:Py $script:Core update @args }
function Get-ClaudeProfilePath { & $script:Py $script:Core path @args }

function Start-ClaudeAuto {
    if ($args.Count -gt 0 -and ($args[0] -eq '-h' -or $args[0] -eq '--help')) {
        Write-Host "usage: claude-auto [CLAUDE ARGS...]"
        Write-Host ""
        Write-Host "Launch Claude on whichever signed-in account has the most headroom."
        Write-Host "Anything you pass is handed to claude itself."
        return
    }
    $pick = & $script:Py $script:Core best --quiet
    if ($LASTEXITCODE -ne 0) { return }
    if (-not $pick) { Write-Error "no signed-in profile with headroom"; return }
    Write-Host "using profile $pick"
    Invoke-ClaudeProfile -Name $pick -Command (@('claude') + $args)
}
function Set-ClaudeStatusLine  { & $script:Py $script:Core statusline @args }

function Invoke-ClaudeProfile {
    [CmdletBinding()] param(
        [Parameter(Position=0,Mandatory)][string]$Name,
        [Parameter(Position=1,ValueFromRemainingArguments,Mandatory)][string[]]$Command)
    $prevDir  = $env:CLAUDE_CONFIG_DIR
    $prevName = $env:CLAUDE_PROFILE_NAME
    try {
        if ($Name -ne "default" -and ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $Name -match '\.\.')) {
        Write-Error "invalid profile name: $Name"; return
    }
    if ($Name -eq "default") {
            Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        } else {
            $dir = Join-Path $script:ProfileHome $Name
            if (-not (Test-Path $dir)) { Write-Error "no such profile: $Name"; return }
            $env:CLAUDE_CONFIG_DIR = $dir; $env:CLAUDE_PROFILE_NAME = $Name
        }
        $exe  = $Command[0]
        $rest = @(if ($Command.Count -gt 1) { $Command[1..($Command.Count - 1)] })
        & $exe @rest
    } finally {
        if ($prevDir)  { $env:CLAUDE_CONFIG_DIR = $prevDir }   else { Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue }
        if ($prevName) { $env:CLAUDE_PROFILE_NAME = $prevName } else { Remove-Item Env:CLAUDE_PROFILE_NAME -ErrorAction SilentlyContinue }
    }
}

function Remove-ClaudeProfile {
    [CmdletBinding()] param([Parameter(Position=0,Mandatory)][string]$Name,[switch]$Yes)
    $extra = if ($Yes) { @("--yes") } else { @() }
    & $script:Py $script:Core remove $Name @extra
    if ($LASTEXITCODE -eq 0 -and $Name -eq $env:CLAUDE_PROFILE_NAME) { Set-ClaudeProfile "default" }
}

# auto-switch on directory change
function Update-ClaudeProfileFromPath {
    $dir = (Get-Location).Path; $name = $null
    while ($dir) {
        $marker = Join-Path $dir ".claude-profile"
        if (Test-Path $marker) { $name = (Get-Content $marker -First 1).Trim(); break }
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    if (-not $name) { $name = if ($env:CLAUDE_DEFAULT_PROFILE) { $env:CLAUDE_DEFAULT_PROFILE } else { "default" } }
    Set-ClaudeProfile $name
}

Set-Alias claude-profile  Set-ClaudeProfile
Set-Alias claude-profiles Get-ClaudeProfiles
Set-Alias claude-sessions Get-ClaudeSessions
Set-Alias claude-handoff  Move-ClaudeSession
Set-Alias claude-profile-remove Remove-ClaudeProfile
Set-Alias claude-doctor   Test-ClaudeProfiles
Set-Alias claude-profile-clone Copy-ClaudeProfile
Set-Alias claude-profile-exec  Invoke-ClaudeProfile
Set-Alias claude-prune    Clear-ClaudeSessions
Set-Alias claude-clear    Remove-ClaudeSessions
Set-Alias claude-best     Find-ClaudeProfile
Set-Alias claude-update   Update-ClaudeProfiles
Set-Alias claude-path     Get-ClaudeProfilePath
Set-Alias claude-statusline Set-ClaudeStatusLine
Set-Alias claude-auto     Start-ClaudeAuto

Register-ArgumentCompleter -CommandName Set-ClaudeProfile -ParameterName Name -ScriptBlock {
    param($c,$p,$word)
    @("default") + (Get-ChildItem $script:ProfileHome -Directory -ErrorAction SilentlyContinue |
        ForEach-Object Name) |
      Where-Object { $_ -like "$word*" } |
      ForEach-Object { [System.Management.Automation.CompletionResult]::new($_,$_,'ParameterValue',$_) }
}

Export-ModuleMember -Function * -Alias *
