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

function Get-ClaudeProfiles { & $script:Py $script:Core status @args }
function Get-ClaudeSessions { & $script:Py $script:Core sessions @args }
function Move-ClaudeSession { & $script:Py $script:Core handoff  @args }

function Test-ClaudeProfiles  { & $script:Py $script:Core doctor @args }
function Copy-ClaudeProfile   { & $script:Py $script:Core clone  @args }

function Invoke-ClaudeProfile {
    [CmdletBinding()] param(
        [Parameter(Position=0,Mandatory)][string]$Name,
        [Parameter(Position=1,ValueFromRemainingArguments,Mandatory)][string[]]$Command)
    $prevDir  = $env:CLAUDE_CONFIG_DIR
    $prevName = $env:CLAUDE_PROFILE_NAME
    try {
        if ($Name -eq "default") {
            Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
        } else {
            $dir = Join-Path $script:ProfileHome $Name
            if (-not (Test-Path $dir)) { Write-Error "no such profile: $Name"; return }
            $env:CLAUDE_CONFIG_DIR = $dir; $env:CLAUDE_PROFILE_NAME = $Name
        }
        & $Command[0] @($Command[1..($Command.Count-1)])
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

Register-ArgumentCompleter -CommandName Set-ClaudeProfile -ParameterName Name -ScriptBlock {
    param($c,$p,$word)
    @("default") + (Get-ChildItem $script:ProfileHome -Directory -ErrorAction SilentlyContinue |
        ForEach-Object Name) |
      Where-Object { $_ -like "$word*" } |
      ForEach-Object { [System.Management.Automation.CompletionResult]::new($_,$_,'ParameterValue',$_) }
}

Export-ModuleMember -Function * -Alias *
