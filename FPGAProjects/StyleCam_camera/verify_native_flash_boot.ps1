param([string]$UartPort='COM19',[int]$Seconds=55,[switch]$ConfigurationResetConfirmed)
$ErrorActionPreference='Stop'
$taskProject=$PSScriptRoot
$taskRecordPath=Join-Path $taskProject 'validation\camera_native_rgb_mirror_flash.json'
$taskRecord=Get-Content -LiteralPath $taskRecordPath -Raw | ConvertFrom-Json
$taskFolder=$taskRecord.log_directory
if(-not [IO.Path]::IsPathRooted($taskFolder)){$taskFolder=Join-Path $taskProject $taskFolder}
if(-not (Test-Path -LiteralPath $taskFolder)){$taskFolder=Join-Path $taskProject ('validation\flash_verify_'+(Get-Date -Format 'yyyyMMdd_HHmmss'));New-Item -ItemType Directory -Path $taskFolder -Force | Out-Null}
$taskRecord.log_directory=$taskFolder
if(-not $taskRecord.independent_readback_bytes_exact -or -not $taskRecord.weight_after_verified){throw 'Complete Flash readback verification first'}
$taskSerial=[System.IO.Ports.SerialPort]::new($UartPort,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
$taskLog=Join-Path $taskRecord.log_directory ('flash_boot_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log')
$taskText='';$taskSent=$false;$taskPassed=$false;$taskPrefixSeen=$false
try {
 $taskSerial.Open();$taskWatch=[Diagnostics.Stopwatch]::StartNew()
 if($ConfigurationResetConfirmed){$taskSerial.Write('cs');$taskSent=$true}
 Write-Output 'Listening for autonomous boot from Flash; press RESET_N or power-cycle the board.'
 while($taskWatch.Elapsed.TotalSeconds -lt $Seconds){
  try {$taskChunk=$taskSerial.ReadExisting()} catch {
   $taskSerial.Dispose()
   $taskSerial=[System.IO.Ports.SerialPort]::new($UartPort,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
   $taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
   try {$taskSerial.Open();if($ConfigurationResetConfirmed){$taskSerial.Write('cs')}} catch {Start-Sleep -Milliseconds 200}
   continue
  }
  $taskText+=$taskChunk
  if($taskChunk){[Console]::Write($taskChunk)}
  if(-not $taskSent -and $taskText -match 'streaming; commands:'){$taskSerial.Write('cs');$taskSent=$true}
  $taskPrefixSeen=$taskText -match 'SPI flash manufacturer=000000ef' -and $taskText -match 'crc 373deed7' -and $taskText -match 'streaming; commands:'
  # A user-confirmed configuration reset also permits a live readback when USB
  # re-enumeration loses the startup prefix. Firmware cannot reach ready=7 and
  # frame processing unless the complete model CRC and all three jobs passed.
  if(($taskPrefixSeen -or $ConfigurationResetConfirmed) -and $taskText -match 'ID=53430a08' -and $taskText -match 'fps=1[45]\.' -and $taskText -match 'ready=7' -and $taskText -match 'camera readback ID=53430a08:' -and $taskText -match '00003e01=00000046' -and $taskText -match '00003e08=00000083' -and $taskText -match '00003e09=00000020' -and $taskText -match '00003e07=00000080' -and $taskText -match '00003221=00000000' -and $taskText -match 'caperr=0 vid_err=0 uf=0 hdmi_err=0 irq_err=0'){$taskPassed=$true;break}
  Start-Sleep -Milliseconds 100
 }
} finally {$taskSerial.Close();$taskSerial.Dispose();$taskText | Set-Content -LiteralPath $taskLog -Encoding utf8}
$taskRecord.flash_boot_verified=$taskPassed;$taskRecord.boot_reload_pending=-not $taskPassed
$taskRecord | Add-Member -NotePropertyName flash_boot_log -NotePropertyValue $taskLog -Force
$taskRecord | Add-Member -NotePropertyName configuration_reset_confirmed_by_user -NotePropertyValue ([bool]$ConfigurationResetConfirmed) -Force
$taskRecord | Add-Member -NotePropertyName boot_prefix_captured -NotePropertyValue ([bool]$taskPrefixSeen) -Force
$taskRecord | Add-Member -NotePropertyName weight_crc_verified_by_successful_startup -NotePropertyValue ([bool]$taskPassed) -Force
if($taskPassed){$taskRecord.stage='Flash boot verified';$taskRecord | Add-Member -NotePropertyName flash_boot_time -NotePropertyValue (Get-Date).ToString('o') -Force}
$taskRecord | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskRecordPath -Encoding utf8
$taskRecord | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRecord.log_directory 'record.json') -Encoding utf8
if($taskPassed){Write-Output 'PASS: autonomous Flash boot, original sensor parameters, model load and streaming verified.'}else{Write-Output 'Flash write/readback passed; physical configuration reset is still required.';exit 3}
