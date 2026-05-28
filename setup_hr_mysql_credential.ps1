param(
    [string]$CredentialPath = ".secrets\hr_mysql_credential.xml",
    [string]$DefaultUser = "root"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$credentialFile = Join-Path $root $CredentialPath
$credentialDir = Split-Path -Parent $credentialFile
New-Item -ItemType Directory -Force -Path $credentialDir | Out-Null

Write-Host "Enter the MySQL credential used for root@127.0.0.1:3306."
Write-Host "Windows will encrypt the password for this Windows user with DPAPI."

$userInput = Read-Host "MySQL user [$DefaultUser]"
if ([string]::IsNullOrWhiteSpace($userInput)) {
    $userInput = $DefaultUser
}

$securePassword = Read-Host "MySQL password" -AsSecureString
$credential = [System.Management.Automation.PSCredential]::new($userInput, $securePassword)
$credential | Export-Clixml -Path $credentialFile

Write-Host "Saved encrypted credential to: $credentialFile"
