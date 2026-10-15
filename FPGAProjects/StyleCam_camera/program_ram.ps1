param(
 [string]$UartPort='COM19',
 [string]$EfinityHome='D:\ELS\efinity\2026.1',
 [string]$Python='python',
 [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$taskRelease=Join-Path $PSScriptRoot '..\烧录文件\20261015_RISCV10_LowLatency_Candidate'
$taskManifest=Get-Content -LiteralPath (Join-Path $taskRelease 'manifest.json') -Raw | ConvertFrom-Json
if($taskManifest.fpga_id -ne '53430a0a' -or $taskManifest.setup_min_ns -le 0 -or $taskManifest.hold_min_ns -le 0){throw 'Unexpected or timing-failing release'}
foreach($taskProperty in $taskManifest.files.PSObject.Properties){
 $taskFile=Join-Path $taskRelease $taskProperty.Name
 if((Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskProperty.Value.sha256){throw "Release file differs: $taskFile"}
}
Write-Output 'PASS: RISCV10 release artifact hashes and final timing.'
if($CheckOnly){return}
$taskBit=(Resolve-Path -LiteralPath (Join-Path $taskRelease 'StyleCam_RISCV10_LowLatency.bit')).Path
$env:EFINITY_HOME=$EfinityHome;$env:PYTHONHOME=Join-Path $EfinityHome 'python311'
$env:EFXPGM_HOME=Join-Path $EfinityHome 'pgm';$env:EFXDBG_HOME=Join-Path $EfinityHome 'debugger'
$env:EFINITY_USER_DIR_INI=Join-Path $env:LOCALAPPDATA 'efinity/user_dir.ini'
$taskSerial=[IO.Ports.SerialPort]::new($UartPort,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false;$taskSerial.RtsEnable=$false
$taskLog='';$taskProgramLog=Join-Path $PSScriptRoot 'validation/latency/ram_program.log'
New-Item -ItemType Directory -Path (Split-Path $taskProgramLog) -Force | Out-Null
try {
 $taskSerial.Open()
 & (Join-Path $EfinityHome 'pgm/bin/ftdi_pgm.bat') -m jtag -b 'Generic Board Profile Using FT4232H' --jtag_clock_freq 1000000 $taskBit *> $taskProgramLog
 if($LASTEXITCODE -ne 0){throw "JTAG programming failed: $taskProgramLog"}
 $taskWatch=[Diagnostics.Stopwatch]::StartNew()
 while($taskWatch.Elapsed.TotalSeconds -lt 35){$taskLog+=$taskSerial.ReadExisting();Start-Sleep -Milliseconds 100}
 if($taskLog -notmatch 'ID=53430a0a' -or $taskLog -notmatch 'ready=7'){throw 'New firmware boot/readiness not observed; inspect UART log'}
 Write-Output 'PASS: RISCV10 RAM boot and ready=7 observed; inspect picture and runtime telemetry.'
} finally {
 if($taskSerial.IsOpen){$taskSerial.Close()};$taskSerial.Dispose()
 [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'validation/latency/ram_boot.log'),$taskLog,[Text.UTF8Encoding]::new($false))
}
