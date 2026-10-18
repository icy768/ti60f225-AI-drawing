param(
 [string]$UartPort='COM19',
 [string]$EfinityHome='D:/ELS/efinity/2026.1',
 [string]$Python='python',
 [switch]$CheckOnly,
 [string]$ReleaseDir=''
)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'program_main_ae_ram.ps1') -UartPort $UartPort -EfinityHome $EfinityHome -CheckOnly:$CheckOnly -ReleaseDir $ReleaseDir
