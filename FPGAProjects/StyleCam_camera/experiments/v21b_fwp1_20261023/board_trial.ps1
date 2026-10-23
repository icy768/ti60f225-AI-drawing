param(
 [string]$EfinityHome='D:/ELS/efinity/2026.1',
 [string]$UartPort='',
 [int]$SampleSeconds=30,
 [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$taskRoot=$PSScriptRoot
$taskCandidate=Join-Path $taskRoot 'delivery/candidates/D1B60_B_FWP1'
$taskBit=Join-Path $taskCandidate 'D1B60_B_FWP1_UNTESTED.bit'
$taskImage=Join-Path $taskCandidate 'D1B60_B_FWP1_UNTESTED.hex'
$taskBlob=Join-Path $taskCandidate 'net_blob.bin'
$taskProfile='Generic Board Profile Using FT4232H'
$taskModelAddress=2097152
$taskUtf8=[Text.UTF8Encoding]::new($false)

function Get-Digest([byte[]]$Data) {
 $taskHash=[Security.Cryptography.SHA256]::Create()
 try { return ([BitConverter]::ToString($taskHash.ComputeHash($Data))).Replace('-','').ToLowerInvariant() }
 finally { $taskHash.Dispose() }
}
function Read-Hex([string]$Path) {
 $taskTokens=[IO.File]::ReadAllText($Path).Split([char[]]" `t`r`n",[StringSplitOptions]::RemoveEmptyEntries)
 $taskBytes=[byte[]]::new($taskTokens.Length)
 for($taskI=0;$taskI -lt $taskTokens.Length;$taskI++) {
  if($taskTokens[$taskI] -notmatch '^[0-9a-fA-F]{2}$'){ throw "Invalid byte HEX token in $Path" }
  $taskBytes[$taskI]=[Convert]::ToByte($taskTokens[$taskI],16)
 }
 return ,$taskBytes
}
function Assert-Same([byte[]]$First,[byte[]]$Second,[string]$Label) {
 if($First.Length -ne $Second.Length -or (Get-Digest $First) -ne (Get-Digest $Second)){ throw "$Label byte comparison failed" }
}

$taskManifest=Get-Content -LiteralPath (Join-Path $taskCandidate 'MANIFEST.json') -Raw | ConvertFrom-Json
if($taskManifest.candidate -ne 'D1B60_B_FWP1' -or $taskManifest.board_tested -or $taskManifest.full_boot_verified){throw 'Unexpected candidate or evidence flags'}
foreach($taskProperty in $taskManifest.files.PSObject.Properties) {
 $taskPath=Join-Path $taskCandidate $taskProperty.Name
 if((Get-Item -LiteralPath $taskPath).Length -ne $taskProperty.Value.bytes -or (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskProperty.Value.sha256){throw "Candidate SHA mismatch: $taskPath"}
}
$taskDesired=Read-Hex $taskImage
$taskConfigBackupLength=[int]([Math]::Ceiling($taskDesired.Length/65536.0)*65536)
if($taskDesired.Length -le 0 -or $taskConfigBackupLength -ge $taskModelAddress){throw 'Configuration erase range overlaps model'}
$taskWeights=[IO.File]::ReadAllBytes($taskBlob)
if($taskWeights.Length -ne 48616 -or (Get-Digest $taskWeights) -ne '84aeb3bae88b4c883a5ff8c8111b289f129359cb82d89df49219a743f14587bd'){throw 'Unexpected model'}
if($CheckOnly) {
 Write-Output "PASS selected candidate SHA/size, model pairing and disjoint Flash regions; config=$($taskDesired.Length) bytes, backup=$taskConfigBackupLength bytes. No hardware accessed."
 return
}
if($SampleSeconds -lt 10 -or $SampleSeconds -gt 600){throw 'SampleSeconds must be 10..600'}

$taskStamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$taskWork=Join-Path $taskRoot "board_$taskStamp"
New-Item -ItemType Directory -Path $taskWork | Out-Null
$taskRecord=[ordered]@{
 model='D1B60_B_FWP1'; commit='7d95dbeaf9b3e9545814be7081390c2f79f2c727';
 started_utc=[DateTime]::UtcNow.ToString('o'); bit_sha256=(Get-FileHash -LiteralPath $taskBit -Algorithm SHA256).Hash.ToLowerInvariant();
 blob_sha256=(Get-Digest $taskWeights); expected_model_crc='20d4d7eb'; configuration_bytes=$taskDesired.Length;
 configuration_backup_bytes=$taskConfigBackupLength; model_backup_bytes=65536; flash_modified=$false;
 backups_verified=$false; independent_readback_exact=$false; new_boot_verified=$false;
 physical_power_cycle_verified=$false; long_term_stability_verified=$false; stage='preflight';
 log_directory=$taskWork
}
function Save-Record { [IO.File]::WriteAllText((Join-Path $taskWork 'record.json'),($taskRecord|ConvertTo-Json -Depth 12),$taskUtf8) }
Save-Record
$env:EFINITY_HOME=$EfinityHome
$env:PYTHONHOME="$EfinityHome/python311"
$env:EFXPGM_HOME="$EfinityHome/pgm"
$env:EFXDBG_HOME="$EfinityHome/debugger"
$env:EFINITY_USER_DIR_INI=Join-Path $env:LOCALAPPDATA 'efinity/user_dir.ini'
$taskExe=Join-Path $EfinityHome 'pgm/bin/ftdi_pgm.bat'
$taskLogNumber=0
function Invoke-Programmer([string[]]$Arguments,[string]$Label) {
 $script:taskLogNumber++
 $taskLog=Join-Path $taskWork ('{0:D2}_{1}.log' -f $script:taskLogNumber,$Label)
 Write-Output "Programmer $Label -> $taskLog" | Out-Host
 & $taskExe @Arguments *> $taskLog
 $taskCode=$LASTEXITCODE
 $taskOutput=[IO.File]::ReadAllText($taskLog)
 $taskRecovered=$Label -match '^program|^restore' -and $taskOutput.Contains('Flash verify successful') -and $taskOutput.LastIndexOf('Flash verify successful') -gt $taskOutput.LastIndexOf('ERROR:')
 if($taskCode -ne 0 -or $taskOutput -match 'Traceback|No USB target' -or ($taskOutput -match 'ERROR:' -and !$taskRecovered)){throw "Programmer failed: $taskLog`n$taskOutput"}
 return $taskOutput
}
function Flash-Args([int]$Address,[int]$Clock=500000) {
 return @('-m','jtag_bridge','-u',$script:taskUrl,'-b',$taskProfile,'--jtag_clock_freq',"$Clock",'--address',"$Address")
}
function Read-Flash([int]$Address,[int]$Length,[string]$Name) {
 $taskPath=Join-Path $taskWork "$Name.hex"
 $taskArgs=(Flash-Args $Address)+@('--jtag_bridge_mode','read','--num_bytes',"$Length",'-o',$taskPath)
 $null=Invoke-Programmer $taskArgs $Name
 $taskData=Read-Hex $taskPath
 if($taskData.Length -ne $Length){throw "Wrong readback length: $Name"}
 return ,$taskData
}
function Write-Flash([int]$Address,[string]$Path,[string]$Name) {
 $taskArgs=(Flash-Args $Address 1000000)+@('--jtag_bridge_mode','all','--verify_method','hostx1',$Path)
 $taskResult=Invoke-Programmer $taskArgs $Name
 if($taskResult -notmatch 'JTAG2SPI programming\.\.\.done' -or $taskResult -notmatch 'Flash verify successful'){throw "Write completion not confirmed: $Name"}
}
function Load-Bridge {
 $taskOutput=Invoke-Programmer @('-m','jtag','-u',$script:taskUrl,'-b',$taskProfile,'--jtag_clock_freq','1000000',(Join-Path $EfinityHome 'pgm/fli/titanium/u10660A79.bit')) 'bridge'
 if($taskOutput -notmatch '10660a79' -or $taskOutput -notmatch 'finished with JTAG programming'){throw 'Unexpected bridge target'}
}

$taskSerial=$null
$taskSuccess=$false
try {
 $taskListing=Invoke-Programmer @('-l') 'list'
 $taskUrls=@([regex]::Matches($taskListing,'ftdi://[^\s]+/1') | ForEach-Object {$_.Value} | Sort-Object -Unique)
 if($taskUrls.Count -ne 1){throw "Expected exactly one Ti60 FTDI/JTAG target; found $($taskUrls.Count)"}
 $script:taskUrl=$taskUrls[0]
 $taskRecord['ftdi_url']=$taskUrl
 if(!$UartPort){
  $taskPorts=@(Get-CimInstance Win32_SerialPort | Where-Object {$_.PNPDeviceID -match 'VID_0403' -or $_.PNPDeviceID -match '^FTDIBUS'})
  if($taskPorts.Count -ne 1){throw 'Specify the confirmed FPGA UART with -UartPort; cannot choose from multiple/no FTDI serial ports'}
  $UartPort=$taskPorts[0].DeviceID
 }
 $taskRecord['uart_port']=$UartPort
 $taskSerial=[IO.Ports.SerialPort]::new($UartPort,115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
 $taskSerial.DtrEnable=$false; $taskSerial.RtsEnable=$false; $taskSerial.ReadBufferSize=262144
 $taskSerial.Open()
 $taskSerial.DiscardInBuffer()
 Save-Record
 Load-Bridge
 $taskRecord['stage']='backing up both Flash regions';Save-Record
 $taskBeforeConfig=Read-Flash 0 $taskConfigBackupLength 'config_before'
 $taskBeforeConfig2=Read-Flash 0 $taskConfigBackupLength 'config_before_verify'
 Assert-Same $taskBeforeConfig $taskBeforeConfig2 'Configuration double backup'
 $taskBeforeModel=Read-Flash $taskModelAddress 65536 'model_before'
 $taskBeforeModel2=Read-Flash $taskModelAddress 65536 'model_before_verify'
 Assert-Same $taskBeforeModel $taskBeforeModel2 'Model double backup'
 $taskRecord['configuration_backup_sha256']=Get-Digest $taskBeforeConfig
 $taskRecord['model_backup_sha256']=Get-Digest $taskBeforeModel
 $taskRecord['backups_verified']=$true
 $taskRecord['stage']='programming paired candidate';Save-Record
 $taskBlobHex=Join-Path $taskWork 'new_model.hex'
 [IO.File]::WriteAllLines($taskBlobHex,([string[]]($taskWeights | ForEach-Object {$_.ToString('X2')})),[Text.Encoding]::ASCII)
 $taskRecord['flash_modified']=$true;Save-Record
 Write-Flash $taskModelAddress $taskBlobHex 'program_model'
 Write-Flash 0 $taskImage 'program_configuration'
 $taskReadConfig=Read-Flash 0 $taskDesired.Length 'config_after'
 Assert-Same $taskDesired $taskReadConfig 'Independent configuration readback'
 $taskReadModel=Read-Flash $taskModelAddress $taskWeights.Length 'model_after'
 Assert-Same $taskWeights $taskReadModel 'Independent model readback'
 $taskRecord['independent_readback_exact']=$true
 $taskRecord['stage']='booting new BIT in RAM after verified Flash write';Save-Record
 $taskSerial.DiscardInBuffer()
 $taskOutput=Invoke-Programmer @('-m','jtag','-u',$taskUrl,'-b',$taskProfile,'--jtag_clock_freq','1000000',$taskBit) 'start_candidate'
 if($taskOutput -notmatch '10660a79' -or $taskOutput -notmatch 'finished with JTAG programming'){throw 'Candidate JTAG start unconfirmed'}
 $taskWatch=[Diagnostics.Stopwatch]::StartNew()
 $taskBoot=''
 while($taskWatch.Elapsed.TotalSeconds -lt 40){
  $taskBoot+=$taskSerial.ReadExisting()
  if($taskBoot -match 'weight blob error|DDR calibration timeout'){throw "New firmware boot failure: $taskBoot"}
  if($taskBoot -match 'ready=7' -and $taskBoot -match 'crc 20d4d7eb'){break}
  Start-Sleep -Milliseconds 100
 }
 [IO.File]::WriteAllText((Join-Path $taskWork 'boot.log'),$taskBoot,$taskUtf8)
 if($taskBoot -notmatch 'ID=53430a0b' -or $taskBoot -notmatch 'crc 20d4d7eb' -or $taskBoot -notmatch 'ready=7'){throw 'New paired firmware/blob boot binding was not observed'}
 $taskRecord['new_boot_verified']=$true
 $taskRecord['boot_mode']='JTAG RAM start of candidate; matching Flash independently verified, autonomous configuration reset not yet tested'
 $taskRecord['stage']='sampling three styles';Save-Record
 Write-Output 'PASS new boot: matching CRC 20d4d7eb and ready=7. Sampling three styles.'
 $taskResults=@()
 foreach($taskStyle in 0,1,2){
  $taskSerial.Write([string]$taskStyle)
  Start-Sleep -Seconds 4
  $taskTransition=$taskSerial.ReadExisting()
  [IO.File]::WriteAllText((Join-Path $taskWork "style${taskStyle}_transition.log"),$taskTransition,$taskUtf8)
  $taskSerial.Write('s')
  $taskWatch.Restart();$taskLog=''
  while($taskWatch.Elapsed.TotalSeconds -lt $SampleSeconds){$taskLog+=$taskSerial.ReadExisting();Start-Sleep -Milliseconds 100}
  [IO.File]::WriteAllText((Join-Path $taskWork "style${taskStyle}.log"),$taskLog,$taskUtf8)
  $taskMatches=[regex]::Matches($taskLog,'fps=(\d+\.\d+) cam=[^\r\n]*?style=(\d+) view=(\d+) ready=(\d+) proc=(\d+) cap=(\d+) skip=(\d+) run_skip=(\d+) caperr=(\d+) vid_err=(\d+) uf=(\d+) hdmi_err=(\d+) irq_err=(\d+)')
  $taskSamples=@($taskMatches | Where-Object {[int]$_.Groups[2].Value -eq $taskStyle})
  if($taskSamples.Count -lt 3){throw "Too few valid status samples for style $taskStyle"}
  $taskFps=@($taskSamples | ForEach-Object {[double]::Parse($_.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)})
  $taskFirst=$taskSamples[0];$taskLast=$taskSamples[-1]
  $taskErrors=@{}
  foreach($taskPair in @(@('caperr',9),@('vid_err',10),@('uf',11),@('hdmi_err',12),@('irq_err',13))){
   $taskErrors[$taskPair[0]]=[long]$taskLast.Groups[$taskPair[1]].Value-[long]$taskFirst.Groups[$taskPair[1]].Value
  }
  $taskRow=[ordered]@{style=$taskStyle;seconds=$SampleSeconds;samples=$taskSamples.Count;fps_min=($taskFps|Measure-Object -Minimum).Minimum;fps_mean=($taskFps|Measure-Object -Average).Average;fps_max=($taskFps|Measure-Object -Maximum).Maximum;processed_delta=([long]$taskLast.Groups[5].Value-[long]$taskFirst.Groups[5].Value);runtime_skipped_delta=([long]$taskLast.Groups[8].Value-[long]$taskFirst.Groups[8].Value);error_deltas=$taskErrors}
  $taskResults+=$taskRow
  $taskRecord['styles']=$taskResults;Save-Record
  Write-Output ($taskRow|ConvertTo-Json -Compress -Depth 4)
  if($taskRow.fps_min -lt 15 -or $taskRow.processed_delta -le 0 -or @($taskErrors.Values|Where-Object {$_ -ne 0}).Count -gt 0){throw "Runtime check failed for style $taskStyle"}
 }
 $taskSerial.Write('0')
 $taskRecord['stage']='paired Flash verified and short three-style JTAG-start trial passed'
 $taskRecord['passed']=$true;$taskRecord['finished_utc']=[DateTime]::UtcNow.ToString('o');Save-Record
 $taskSuccess=$true
 Write-Output "PASS FWP1 board short trial; showing Van Gogh. Evidence: $taskWork"
} catch {
 $taskRecord['failure']=$_ | Out-String
 $taskRecord['passed']=$false
 Save-Record
 if($taskRecord.flash_modified -and $taskRecord.backups_verified -and !$taskSuccess){
  try {
   $taskRecord['stage']='restoring double-verified original Flash backups';Save-Record
   Load-Bridge
   Write-Flash $taskModelAddress (Join-Path $taskWork 'model_before.hex') 'restore_model'
   Write-Flash 0 (Join-Path $taskWork 'config_before.hex') 'restore_configuration'
   $taskRestoredModel=Read-Flash $taskModelAddress 65536 'restored_model'
   $taskRestoredConfig=Read-Flash 0 $taskConfigBackupLength 'restored_configuration'
   Assert-Same $taskBeforeModel $taskRestoredModel 'Restored original model'
   Assert-Same $taskBeforeConfig $taskRestoredConfig 'Restored original configuration'
   $taskRecord['original_flash_restored']=$true
   $taskRecord['configuration_reset_required']=$true
  } catch { $taskRecord['restore_error']=$_ | Out-String }
 }
 Save-Record
 throw
} finally {
 if($taskSerial){
  if($taskSerial.IsOpen){
   $taskTail=$taskSerial.ReadExisting()
   [IO.File]::WriteAllText((Join-Path $taskWork 'uart_tail.log'),$taskTail,$taskUtf8)
   $taskSerial.Close()
  }
  $taskSerial.Dispose()
 }
}
