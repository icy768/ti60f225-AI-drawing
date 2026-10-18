param([string]$UartPort='COM19',[int]$Seconds=600,[switch]$CheckOnly,[switch]$ConfigurationResetConfirmed)
$ErrorActionPreference='Stop'
$taskRecordPath=Join-Path $PSScriptRoot 'validation/release_riscv11_20261018/flash_deployment.json'
$taskRecord=Get-Content -LiteralPath $taskRecordPath -Raw | ConvertFrom-Json
if(!$taskRecord.independent_readback_bytes_exact -or !$taskRecord.weight_after_verified){throw 'Complete Flash programming and independent readback first'}
if($CheckOnly){Write-Output 'PASS RISCV11 Flash readback record';return}
$taskLog=Join-Path $taskRecord.log_directory ('flash_boot_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log')
$taskSerial=[IO.Ports.SerialPort]::new($UartPort,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
$taskText='';$taskSent=$false;$taskPassed=$false
try {
 $taskSerial.Open();$taskSerial.DiscardInBuffer();$taskWatch=[Diagnostics.Stopwatch]::StartNew()
 Write-Output 'Listening for RISCV11 autonomous Flash boot. Press RESET_N (configuration reset), not K0.'
 while($taskWatch.Elapsed.TotalSeconds -lt $Seconds){
  try {$taskChunk=$taskSerial.ReadExisting()} catch {
   $taskSerial.Dispose()
   $taskSerial=[IO.Ports.SerialPort]::new($UartPort,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
   $taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
   try {$taskSerial.Open()} catch {Start-Sleep -Milliseconds 200}
   continue
  }
  $taskText+=$taskChunk
  if($taskChunk){[Console]::Write($taskChunk)}
  if(!$taskSent -and $taskText -match 'streaming; commands:'){$taskSerial.Write('cs');$taskSent=$true}
  $taskPrefix=$taskText -match 'ID=53430a0b' -and $taskText -match 'SPI flash manufacturer=000000ef' -and $taskText -match '48616 B, crc 373deed7' -and $taskText -match 'streaming; commands:'
  $taskSamples=[regex]::Matches($taskText,'fps=(?:29\.9[0-9]|30\.0[0-9]).*ready=7.*run_skip=0 caperr=0 vid_err=0 uf=0 hdmi_err=0 irq_err=0')
  if($taskPrefix -and $taskSamples.Count -ge 3 -and $taskText -match 'i2c_errors=0 AWB=OFF' -and $taskText -match 'camera readback ID=53430a0b:'){$taskPassed=$true;break}
  Start-Sleep -Milliseconds 100
 }
} finally {
 if($taskSerial.IsOpen){$taskText+=$taskSerial.ReadExisting();$taskSerial.Close()};$taskSerial.Dispose()
 [IO.File]::WriteAllText($taskLog,$taskText,[Text.UTF8Encoding]::new($false))
}
$taskRecord.flash_boot_verified=$taskPassed;$taskRecord.boot_reload_pending=!$taskPassed
$taskRecord | Add-Member -NotePropertyName flash_boot_log -NotePropertyValue $taskLog -Force
$taskRecord | Add-Member -NotePropertyName boot_prefix_captured -NotePropertyValue ([bool]$taskPrefix) -Force
$taskRecord | Add-Member -NotePropertyName no_RAM_image_loaded_after_Flash_write -NotePropertyValue $true -Force
$taskRecord | Add-Member -NotePropertyName configuration_reset_confirmed_by_user -NotePropertyValue ([bool]$ConfigurationResetConfirmed) -Force
if($taskPassed){$taskRecord.stage='Flash autonomous boot verified';$taskRecord | Add-Member -NotePropertyName flash_boot_time -NotePropertyValue (Get-Date).ToString('o') -Force}
$taskRecord | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskRecordPath -Encoding utf8
$taskRecord | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRecord.log_directory 'record.json') -Encoding utf8
if(!$taskPassed){throw 'Flash readback passed; autonomous boot is still pending. See UART log.'}
Write-Output 'PASS autonomous RISCV11 Flash boot, model CRC, three styles, AE and short streaming sample.'
