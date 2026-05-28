param(
    [string]$TaskName = "Monthly HR Extract And Report",
    [string]$DayOfMonth = "1",
    [string]$Time = "09:00"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $root "run_monthly_hr_pipeline.ps1"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Runner script not found: $runner"
}

$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$taskRun = "`"$powershell`" -NoProfile -ExecutionPolicy Bypass -File `"$runner`""

Write-Host "Registering monthly task:"
Write-Host "  Name: $TaskName"
Write-Host "  Day:  $DayOfMonth"
Write-Host "  Time: $Time"
Write-Host "  Run:  $taskRun"

schtasks.exe /Create /F /SC MONTHLY /D $DayOfMonth /ST $Time /TN $TaskName /TR $taskRun | Out-Host

Write-Host "Task registered. You can inspect it in Windows Task Scheduler."
