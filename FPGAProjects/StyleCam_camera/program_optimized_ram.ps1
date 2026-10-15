param([string]$UartPort='COM19',[string]$EfinityHome='D:\ELS\efinity\2026.1',[switch]$CheckOnly)
& (Join-Path $PSScriptRoot 'program_ram.ps1') -UartPort $UartPort -EfinityHome $EfinityHome -CheckOnly:$CheckOnly
