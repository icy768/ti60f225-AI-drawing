param([string]$UartPort='COM19',[switch]$CheckOnly,[string]$ReleaseDir='',[string]$EfinityHome='D:/ELS/efinity/2026.1')
$ErrorActionPreference='Stop'
$taskRelease=if($ReleaseDir){$ReleaseDir}else{Join-Path $PSScriptRoot '../烧录文件/20261018_RISCV11_Main_AE_IN4_Release'}
$taskManifest=Get-Content -LiteralPath (Join-Path $taskRelease 'manifest.json') -Raw | ConvertFrom-Json
if($taskManifest.fpga_id -ne '53430a0b' -or $taskManifest.setup_min_ns -le 0 -or $taskManifest.hold_min_ns -le 0){throw 'Unexpected or failing AE trial'}
foreach($taskProperty in $taskManifest.files.PSObject.Properties){
 $taskFile=Join-Path $taskRelease $taskProperty.Name
 if((Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskProperty.Value.sha256){throw "Release hash mismatch: $taskFile"}
}
if($CheckOnly){Write-Output 'PASS RISCV11 release hashes/timing';return}
$taskHome=$EfinityHome
$env:EFINITY_HOME=$taskHome;$env:PYTHONHOME="$taskHome/python311"
$env:EFXPGM_HOME="$taskHome/pgm";$env:EFXDBG_HOME="$taskHome/debugger"
$env:EFINITY_USER_DIR_INI=Join-Path $env:LOCALAPPDATA 'efinity/user_dir.ini'
$taskOut=Join-Path $PSScriptRoot 'validation/main_ae'
New-Item -ItemType Directory -Path $taskOut -Force | Out-Null
$taskStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$taskSerial=[IO.Ports.SerialPort]::new($UartPort,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
$taskLog=''
try {
 $taskSerial.Open();$taskSerial.DiscardInBuffer()
 $taskBitName=if($taskManifest.bit_file){$taskManifest.bit_file}else{'StyleCam_RISCV11_Main_AE_Only.bit'}
 $taskBit=(Resolve-Path -LiteralPath (Join-Path $taskRelease $taskBitName)).Path
 & "$taskHome/pgm/bin/ftdi_pgm.bat" -m jtag -b 'Generic Board Profile Using FT4232H' --jtag_clock_freq 1000000 $taskBit *> (Join-Path $taskOut "ram_program_$taskStamp.log")
 if($LASTEXITCODE -ne 0){throw 'JTAG download failed; inspect program log'}
 Write-Output 'JTAG download completed; collecting AE boot and runtime telemetry.'
 $taskWatch=[Diagnostics.Stopwatch]::StartNew();$taskReadback=$false
 while($taskWatch.Elapsed.TotalSeconds -lt 35){
  $taskLog+=$taskSerial.ReadExisting()
  if(!$taskReadback -and $taskWatch.Elapsed.TotalSeconds -ge 28){$taskSerial.Write('c');$taskReadback=$true}
  Start-Sleep -Milliseconds 100
 }
 if($taskLog -notmatch 'ID=53430a0b' -or $taskLog -notmatch 'ready=7' -or $taskLog -notmatch 'AWB=OFF'){throw 'AE firmware boot/readiness not observed'}
 if($taskLog -match 'AE .*i2c_errors=[1-9]'){throw 'AE I2C errors observed'}
 Write-Output 'PASS RISCV11 AE-only RAM boot, ready=7, AE telemetry and no AE I2C errors.'
 Write-Output $taskLog
} finally {
 if($taskSerial.IsOpen){$taskLog+=$taskSerial.ReadExisting();$taskSerial.Close()};$taskSerial.Dispose()
 [IO.File]::WriteAllText((Join-Path $taskOut "ram_boot_$taskStamp.log"),$taskLog,[Text.UTF8Encoding]::new($false))
}
