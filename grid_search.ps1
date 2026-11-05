<#
.SYNOPSIS
    PICARD Hyperparameter Grid Search & Benchmarking Utility for Windows PowerShell.
.DESCRIPTION
    Runs a systematic grid search across hyperparameter combinations for any
    given algorithm, validating against its algorithm specification manifest.
    Executes experiments, extracts metrics, and generates benchmark summaries.
.EXAMPLE
    .\grid_search.ps1 -Manifest PICARD2\backend\scripts\manifests\codrift.json -Param "numTrees=10,20" -DryRun
.EXAMPLE
    .\grid_search.ps1 -Manifest PICARD2\backend\scripts\manifests\supervisedmlrf.json -Grid examples\grids\supervisedmlrf_grid.json -Url http://localhost:8000 -Username admin -Password secret -ScriptName "SupervisedMLRF" -DatasetName "sample.csv"
#>

[CmdletBinding()]
param(
    [Alias("m")]
    [string]$Manifest,

    [Alias("g")]
    [string]$Grid,

    [Alias("p")]
    [string[]]$Param,

    [Alias("a")]
    [switch]$Auto,

    [switch]$DryRun,

    [ValidateSet("api", "direct", "docker")]
    [string]$Mode = "api",

    [Alias("u")]
    [string]$Url = "http://localhost:8000",

    [string]$Username,
    [string]$Password,

    [Alias("s")]
    [string]$ScriptId,
    [string]$ScriptName,

    [Alias("d")]
    [string]$DatasetId,
    [string]$DatasetName,

    [int]$PollInterval = 3,
    [int]$Timeout = 3600,

    [string]$ScriptFile,
    [string]$DatasetFile,
    [string]$MainClass,
    [string]$SparkMaster = "spark://spark-master:7077",
    [string]$DockerContainer = "spark-master",

    [Alias("o")]
    [string]$OutputDir,

    [string]$Metric = "accuracy",
    [switch]$VerboseOutput,
    [switch]$Help
)

if ($Help) {
    Get-Help $MyInvocation.MyCommand.Path -Full
    exit 0
}

# Resolve Python interpreter
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error "Python 3 is required to run grid search on Windows."
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyScript = Join-Path $scriptDir "grid_search.py"

# Build arguments for Python runner
$pyArgs = @()
if ($Manifest) { $pyArgs += @("-m", $Manifest) }
if ($Grid) { $pyArgs += @("-g", $Grid) }
if ($Param) {
    foreach ($item in $Param) {
        $pyArgs += @("-p", $item)
    }
}
if ($Auto) { $pyArgs += @("-a") }
if ($DryRun) { $pyArgs += @("--dry-run") }
if ($Mode) { $pyArgs += @("--mode", $Mode) }
if ($Url) { $pyArgs += @("-u", $Url) }
if ($Username) { $pyArgs += @("--username", $Username) }
if ($Password) { $pyArgs += @("--password", $Password) }
if ($ScriptId) { $pyArgs += @("-s", $ScriptId) }
if ($ScriptName) { $pyArgs += @("--script-name", $ScriptName) }
if ($DatasetId) { $pyArgs += @("-d", $DatasetId) }
if ($DatasetName) { $pyArgs += @("--dataset-name", $DatasetName) }
if ($PollInterval) { $pyArgs += @("--poll-interval", $PollInterval) }
if ($Timeout) { $pyArgs += @("--timeout", $Timeout) }
if ($ScriptFile) { $pyArgs += @("--script-file", $ScriptFile) }
if ($DatasetFile) { $pyArgs += @("--dataset-file", $DatasetFile) }
if ($MainClass) { $pyArgs += @("--main-class", $MainClass) }
if ($SparkMaster) { $pyArgs += @("--spark-master", $SparkMaster) }
if ($DockerContainer) { $pyArgs += @("--docker-container", $DockerContainer) }
if ($OutputDir) { $pyArgs += @("-o", $OutputDir) }
if ($Metric) { $pyArgs += @("--metric", $Metric) }
if ($VerboseOutput) { $pyArgs += @("-v") }

# Run cross-platform Python implementation
& $pythonCmd.Source $pyScript @pyArgs
exit $LASTEXITCODE
