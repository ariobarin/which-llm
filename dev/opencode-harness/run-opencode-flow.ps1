param(
    [string[]]$Case = @("pick", "compare", "profile", "slug", "frontier", "export"),
    [string]$Model = "bigmodel/glm-5.2"
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

$previousConfigContent = $env:OPENCODE_CONFIG_CONTENT
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
        if ($Text -match "ProviderAuthError|API key is missing|401|authentication") {
            Write-Warning "$Name failed before tool use because opencode provider auth is not visible to this shell"
            $HadFailure = $true
            continue
        }

        $Observed = @()
        foreach ($Script in $KnownScripts) {
            if ($Text -match [regex]::Escape($Script)) {
                $Observed += $Script
            }
        }
        if ($Observed.Count -eq 0) {
            $Observed = @("(none)")
        }
        Write-Host "$Name scripts: $($Observed -join ', ')"
    }
}
finally {
    $env:OPENCODE_CONFIG_CONTENT = $previousConfigContent
}

if ($HadFailure) {
    exit 2
}
