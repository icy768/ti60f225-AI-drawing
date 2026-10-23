param(
    [switch]$CheckOnly,
    [string]$EfinityHome = 'D:/ELS/efinity/2026.1'
)
$ErrorActionPreference = 'Stop'
$candidateDirectory = Join-Path $PSScriptRoot 'fpga'
$manifestPath = Join-Path $candidateDirectory 'manifest.json'
if (!(Test-Path -LiteralPath $manifestPath)) { throw 'FPGA candidate is not ready: no completed manifest.' }
$candidate = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$candidate.phone_preview_enabled -or !$candidate.main_sources_unchanged) { throw 'Unexpected candidate configuration.' }
if ($candidate.setup_min_ns -le 0 -or $candidate.hold_min_ns -le 0) { throw 'FPGA timing has not passed.' }
if ($candidate.pin_mapping.uart_rx -ne 'GPIOL_04 / B3 / J28-37' -or $candidate.pin_mapping.stream_tx -ne 'GPIOL_06 / C3 / J28-39') { throw 'Unexpected J7 pin mapping.' }
foreach ($entry in $candidate.files.PSObject.Properties) {
    $filePath = Join-Path $candidateDirectory $entry.Name
    if ((Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) { throw "Candidate hash mismatch: $filePath" }
}
Write-Output "PASS: candidate hashes, J7 pins and routed timing. Setup=$($candidate.setup_min_ns)ns Hold=$($candidate.hold_min_ns)ns"
if ($CheckOnly) { Write-Output 'Offline check only. No USB or serial device accessed.'; return }
$programmer = Join-Path $EfinityHome 'pgm/bin/ftdi_pgm.bat'
if (!(Test-Path -LiteralPath $programmer)) { throw "Efinity JTAG tool missing: $programmer" }
$bitPath = Join-Path $candidateDirectory $candidate.bit_file
$logPath = Join-Path $PSScriptRoot 'fpga_ram_program.log'
$environmentKeys = @('EFINITY_HOME','PYTHONHOME','EFXPGM_HOME','EFXDBG_HOME','EFINITY_USER_DIR_INI')
$savedEnvironment = @{}
foreach ($key in $environmentKeys) { $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key,'Process') }
try {
    $env:EFINITY_HOME = $EfinityHome
    $env:PYTHONHOME = Join-Path $EfinityHome 'python311'
    $env:EFXPGM_HOME = Join-Path $EfinityHome 'pgm'
    $env:EFXDBG_HOME = Join-Path $EfinityHome 'debugger'
    $env:EFINITY_USER_DIR_INI = Join-Path $env:LOCALAPPDATA 'efinity/user_dir.ini'
    Write-Output 'Programming FPGA volatile configuration RAM through JTAG; configuration Flash and model Flash are not written.'
    & $programmer -m jtag -b 'Generic Board Profile Using FT4232H' --jtag_clock_freq 1000000 $bitPath *> $logPath
    if ($LASTEXITCODE -ne 0) { throw "JTAG download failed. Inspect $logPath" }
} finally {
    foreach ($key in $environmentKeys) { [Environment]::SetEnvironmentVariable($key,$savedEnvironment[$key],'Process') }
}
Write-Output "JTAG tool completed. Verify the HDMI image, control actions and preview using the tutorial. Log: $logPath"
