param(
    [string[]]$Case = @("pick", "compare", "profile", "slug", "frontier", "export")
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$PluginDir = Join-Path $RepoRoot "plugins\which-llm"
$OutputDir = Join-Path $PSScriptRoot "outputs"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$KnownScripts = @(
    "pick.py",
    "compare.py",
    "profile.py",
    "slug.py",
    "frontier.py",
    "export.py",
    "query.py",
    "plot_pareto.py"
)
$HadFailure = $false

function Get-BashCommands {
    param([string]$Path)
    $commands = @()
    foreach ($line in Get-Content -LiteralPath $Path) {
        try {
            $event = $line | ConvertFrom-Json
        }
        catch {
            continue
        }
        if ($event.type -eq "assistant" -and $event.message.content) {
            foreach ($item in $event.message.content) {
                if ($item.type -eq "tool_use" -and
                    $item.name -match "^(Bash|bash)$" -and
                    $item.input.command) {
                    $commands += [string]$item.input.command
                }
            }
        }
        if ($event.type -eq "tool_use" -and
            $event.part.tool -match "^(Bash|bash)$" -and
            $event.part.state.input.command) {
            $commands += [string]$event.part.state.input.command
        }
    }
    return $commands
}

foreach ($Name in $Case) {
    $PromptPath = Join-Path $PSScriptRoot "prompts\$Name.txt"
    if (-not (Test-Path -LiteralPath $PromptPath)) {
        throw "missing prompt: $PromptPath"
    }

    $OutPath = Join-Path $OutputDir "$Name.stream.jsonl"
    $DebugPath = Join-Path $OutputDir "$Name.debug.log"
    $Prompt = Get-Content -LiteralPath $PromptPath -Raw

    Write-Host "running $Name"
    & claude -p `
        --no-session-persistence `
        --output-format stream-json `
        --verbose `
        --plugin-dir $PluginDir `
        --add-dir $RepoRoot `
        --permission-mode bypassPermissions `
        --tools "Read,Bash" `
        --debug-file $DebugPath `
        $Prompt 2>&1 | Tee-Object -FilePath $OutPath | Out-Null

    $Text = Get-Content -LiteralPath $OutPath -Raw
    if ($Text -match "authentication_failed|Failed to authenticate|API Error: 401") {
        Write-Warning "$Name failed before tool use because Claude provider auth returned 401"
        $HadFailure = $true
        continue
    }
    $Commands = Get-BashCommands -Path $OutPath
    $Observed = @()
    foreach ($Script in $KnownScripts) {
        if (($Commands -join "`n") -match [regex]::Escape($Script)) {
            $Observed += $Script
        }
    }
    if ($Commands.Count -eq 0) {
        $Commands = @("(none)")
    }
    if ($Observed.Count -eq 0) {
        $Observed = @("(none)")
    }
    Write-Host "$Name bash commands: $($Commands -join ' ; ')"
    Write-Host "$Name scripts: $($Observed -join ', ')"
}

if ($HadFailure) {
    exit 2
}
