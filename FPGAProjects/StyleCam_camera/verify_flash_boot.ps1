param([string]$UartPort='COM19',[int]$Seconds=600,[switch]$CheckOnly,[switch]$ConfigurationResetConfirmed)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'verify_main_ae_flash_boot.ps1') -UartPort $UartPort -Seconds $Seconds -CheckOnly:$CheckOnly -ConfigurationResetConfirmed:$ConfigurationResetConfirmed
