param([string]$UartPort='COM19',[string]$EfinityHome='D:\ELS\efinity\2026.1')
$ErrorActionPreference='Stop'
# Current accepted release: ID 53430a08.
& (Join-Path $PSScriptRoot 'program_native_ram.ps1') -UartPort $UartPort -EfinityHome $EfinityHome
