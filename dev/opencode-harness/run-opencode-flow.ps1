param(
    [string[]]$Case = @("pick", "compare", "profile", "slug", "frontier", "export"),
    [string]$Model = "bigmodel/glm-5.2",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
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

function Import-EnvKey {
    param(
        [string]$Path,
        [string]$Name
    )
    if (-not $Path) {
        return
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "env file not found: $Path"
    }
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -First 1
    if (-not $line) {
        return
    }
    $value = ($line -split "=", 2)[1].Trim()
    $value = $value.Trim('"').Trim("'")
    if ($value) {
        Set-Item -Path "Env:$Name" -Value $value
        Write-Host "$Name loaded from env file"
    }
}

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
        if ($event.type -eq "tool_use" -and
            $event.part.tool -eq "bash" -and
            $event.part.state.input.command) {
            $commands += [string]$event.part.state.input.command
        }
    }
    return $commands
}

$previousBigModelKey = $env:BIGMODEL_API_KEY
$previousConfigContent = $env:OPENCODE_CONFIG_CONTENT
Import-EnvKey -Path $EnvFile -Name "BIGMODEL_API_KEY"
$env:OPENCODE_CONFIG_CONTENT = '{"skills":{"paths":["skills"]}}'

try {
    $SkillProbe = opencode debug skill 2>&1 | Out-String
    if ($SkillProbe -notmatch '"name": "which-llm"') {
        throw "opencode did not load the which-llm skill from the repo skills path"
    }

    foreach ($Name in $Case) {
        $PromptPath = Join-Path $PSScriptRoot "prompts\$Name.txt"
        if (-not (Test-Path -LiteralPath $PromptPath)) {
            throw "missing prompt: $PromptPath"
        }

        $OutPath = Join-Path $OutputDir "$Name.jsonl"
        $Prompt = Get-Content -LiteralPath $PromptPath -Raw

        Write-Host "running $Name"
        Push-Location $RepoRoot
        try {
            opencode run `
                --format json `
                --model $Model `
                --dangerously-skip-permissions `
                $Prompt 2>&1 | Tee-Object -FilePath $OutPath | Out-Null
        }
        finally {
            Pop-Location
        }

        $Text = Get-Content -LiteralPath $OutPath -Raw
        if ($Text -match "ProviderAuthError|API key is missing|Unauthorized|authentication_failed|Failed to authenticate") {
            Write-Warning "$Name failed before tool use because opencode provider auth is not visible to this shell"
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
}
finally {
    $env:OPENCODE_CONFIG_CONTENT = $previousConfigContent
    $env:BIGMODEL_API_KEY = $previousBigModelKey
}

if ($HadFailure) {
    exit 2
}
