param(
    [string]$CredentialPath = ".secrets\hr_mysql_credential.xml",
    [string]$OutputDate = (Get-Date -Format "yyyyMMddHHmm"),
    [string]$Database = "hr",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 3306,
    [switch]$SkipReport
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$credentialFile = Join-Path $root $CredentialPath
$mysqlUser = $null
$mysqlPassword = $null

if (Test-Path -LiteralPath $credentialFile) {
    $credential = Import-Clixml -Path $credentialFile
    $mysqlUser = $credential.UserName
    $mysqlPassword = $credential.GetNetworkCredential().Password
} elseif ($env:HR_MYSQL_USER -and $env:HR_MYSQL_PASSWORD) {
    $mysqlUser = $env:HR_MYSQL_USER
    $mysqlPassword = $env:HR_MYSQL_PASSWORD
} else {
    throw "MySQL credential not found. Run setup_hr_mysql_credential.ps1 locally, or set HR_MYSQL_USER and HR_MYSQL_PASSWORD as environment variables/GitHub Secrets."
}

$mysqlshConfig = Join-Path $root ".mysqlsh"
New-Item -ItemType Directory -Force -Path $mysqlshConfig | Out-Null
$env:MYSQLSH_USER_CONFIG_HOME = $mysqlshConfig

$mysqlshCommand = (Get-Command mysqlsh -ErrorAction Stop).Source
$pythonCommand = (Get-Command python -ErrorAction Stop).Source

$extractDir = Join-Path $root "extracted_data"
$reportDir = Join-Path $root "reports"
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$extractFile = Join-Path $extractDir "hr_employee_connected_extract_$OutputDate.csv"

Write-Host "Running HR SQL extract..."
$jsonLines = & $mysqlshCommand `
    --quiet-start=2 `
    --log-sql=off `
    --sqlc `
    --user=$mysqlUser `
    --host=$HostName `
    --port=$Port `
    --database=$Database `
    --password="$mysqlPassword" `
    --result-format=json/array `
    --file "HR_template.sql"

if ($LASTEXITCODE -ne 0) {
    throw ($jsonLines -join "`n")
}

$start = -1
$end = -1
for ($i = 0; $i -lt $jsonLines.Count; $i++) {
    if ($jsonLines[$i].Trim() -eq "[") {
        $start = $i
        break
    }
}
for ($i = $jsonLines.Count - 1; $i -ge 0; $i--) {
    if ($jsonLines[$i].Trim() -eq "]") {
        $end = $i
        break
    }
}
if ($start -lt 0 -or $end -lt $start) {
    throw "Could not locate the JSON result set in mysqlsh output."
}

$rows = ($jsonLines[$start..$end] -join "`n") | ConvertFrom-Json
if (-not $rows -or @($rows).Count -eq 0) {
    throw "SQL extract returned no rows."
}

$exportCsvParams = @{
    Path = $extractFile
    NoTypeInformation = $true
}
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $exportCsvParams.Encoding = "utf8BOM"
} else {
    $exportCsvParams.Encoding = "UTF8"
}

$rows | Export-Csv @exportCsvParams
Write-Host "CSV written: $extractFile"
Write-Host "Rows: $(@($rows).Count)"

if ($SkipReport) {
    Write-Host "Report generation skipped."
    Write-Host "HR SQL extract completed."
    return
}

Write-Host "Generating HR report..."
& $pythonCommand "generate_hr_report.py" --input-dir $extractDir --output-dir $reportDir
if ($LASTEXITCODE -ne 0) {
    throw "generate_hr_report.py failed."
}

Write-Host "Monthly HR pipeline completed."
