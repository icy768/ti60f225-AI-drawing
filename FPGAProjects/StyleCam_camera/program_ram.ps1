param([string]$UartPort='COM19',[string]$EfinityHome='D:\ELS\efinity\2026.1')
$ErrorActionPreference='Stop'
$taskProject=$PSScriptRoot
$taskBit=Join-Path $taskProject 'outflow\ti60f225_oob.bit'
if(-not (Test-Path -LiteralPath $taskBit)){$taskBit=Join-Path $taskProject '..\烧录文件\20261008_RISCV_HMirror\StyleCam_RISCV_HMirror_53430a04.bit'}
$taskChecked=Get-Content -LiteralPath (Join-Path $taskProject 'validation\camera_mirror_only.json') -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskBit -Algorithm SHA256).Hash.ToLower() -ne $taskChecked.bit_sha256){throw 'Bitstream differs from checked build'}
if(-not $taskChecked.rgb_sim_passed -or $taskChecked.setup_min_ns -le 0 -or $taskChecked.hold_min_ns -le 0){throw 'Build validation missing or failed'}
$env:EFINITY_HOME=$EfinityHome
$env:PYTHONHOME=$EfinityHome+'\python311'
$env:EFXPGM_HOME=$EfinityHome+'\pgm'
$env:EFXDBG_HOME=$EfinityHome+'\debugger'
$env:EFINITY_USER_DIR_INI=$env:LOCALAPPDATA+'\efinity\user_dir.ini'
$taskCli=Join-Path $EfinityHome 'pgm\bin\ftdi_pgm.bat'
$taskListing=(& $taskCli -l 2>&1 | Out-String)
if($LASTEXITCODE -ne 0){throw $taskListing}
$taskUrls=@([regex]::Matches($taskListing,'ftdi://[^\s]+/1') | ForEach-Object Value | Select-Object -Unique)
if($taskUrls.Count -ne 1){throw ('Expected one JTAG target: '+$taskListing)}
$taskStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$taskLog=Join-Path $taskProject ('validation\camera_mirror_jtag_'+$taskStamp+'.log')
$taskErr=Join-Path $taskProject ('validation\camera_mirror_jtag_'+$taskStamp+'.stderr.log')
$taskUartLog=Join-Path $taskProject ('validation\camera_mirror_boot_'+$taskStamp+'.log')
$taskSerial=[System.IO.Ports.SerialPort]::new($UartPort,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$taskSerial.DtrEnable=$false
$taskSerial.RtsEnable=$false
try {
 $taskSerial.Open();$taskSerial.DiscardInBuffer()
 $taskArgs='/c call "'+$taskCli+'" -m jtag -u '+$taskUrls[0]+' -b "Generic Board Profile Using FT4232H" --jtag_clock_freq 1000000 "'+$taskBit+'"'
 $taskPgm=Start-Process -FilePath $env:ComSpec -ArgumentList $taskArgs -WorkingDirectory $taskProject -WindowStyle Hidden -RedirectStandardOutput $taskLog -RedirectStandardError $taskErr -PassThru
 $taskWatch=[Diagnostics.Stopwatch]::StartNew();$taskUart=''
 while($taskWatch.Elapsed.TotalSeconds -lt 40){$taskChunk=$taskSerial.ReadExisting();$taskUart+=$taskChunk;if($taskChunk){Write-Output $taskChunk};Start-Sleep -Milliseconds 90}
 $taskUart | Set-Content -LiteralPath $taskUartLog -Encoding utf8
 if(-not $taskPgm.HasExited){throw 'JTAG programmer still running; inspect log'}
 if($taskPgm.ExitCode -ne 0){throw ('JTAG exit '+$taskPgm.ExitCode)}
 $taskResult=Get-Content -LiteralPath $taskLog -Raw
 if($taskResult -notmatch '0x10660A79' -or $taskResult -notmatch 'finished with JTAG programming'){throw $taskResult}
 if($taskUart -notmatch 'ID=53430a04' -or $taskUart -notmatch 'SC431HAI ready, 193 commands' -or $taskUart -notmatch 'streaming; commands:'){throw 'UART did not confirm new camera configuration startup'}
 Get-Content -LiteralPath $taskLog -Tail 8
 [ordered]@{time=(Get-Date).ToString('o');mode='temporary JTAG RAM configuration';Flash_modified=$false;bit_sha256=$taskChecked.bit_sha256;fpga_id='0x53430a04';uart_port=$UartPort;jtag_log=$taskLog;uart_log=$taskUartLog;boot_verified=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskProject 'validation\camera_mirror_programming.json') -Encoding utf8
} finally {$taskSerial.Close();$taskSerial.Dispose()}
