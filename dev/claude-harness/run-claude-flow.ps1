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

if ($HadFailure) {
    exit 2
}
