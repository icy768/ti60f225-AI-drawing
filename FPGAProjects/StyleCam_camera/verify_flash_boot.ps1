param([string]$UartPort='COM19',[int]$Seconds=55,[switch]$ConfigurationResetConfirmed)
$ErrorActionPreference='Stop'
# Current accepted release: ID 53430a08.
& (Join-Path $PSScriptRoot 'verify_native_flash_boot.ps1') -UartPort $UartPort -Seconds $Seconds -ConfigurationResetConfirmed:$ConfigurationResetConfirmed
