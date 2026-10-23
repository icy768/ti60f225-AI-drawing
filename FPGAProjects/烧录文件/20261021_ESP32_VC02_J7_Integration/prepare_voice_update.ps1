param(
    [string]$FirmwarePath = '',
    [string]$VoiceToolRoot = 'C:/Users/lingye/Desktop/FPGA/FPGAProjects/tools/vc02'
)
$ErrorActionPreference = 'Stop'
if (!$FirmwarePath) { $FirmwarePath = Join-Path $PSScriptRoot 'voice/uni_app_release_update.bin' }
if (!(Test-Path -LiteralPath $FirmwarePath -PathType Leaf)) { throw "Generate and download the project UART update file first, then place it at: $FirmwarePath" }
$sourceFile = Get-Item -LiteralPath $FirmwarePath
if ($sourceFile.Name -ne 'uni_app_release_update.bin' -or $sourceFile.Length -eq 0) { throw 'Expected a nonempty uni_app_release_update.bin, not a complete JTAG image or a CSV.' }
$toolDirectory = Join-Path $VoiceToolRoot 'serial-update-tool/Hummingbird-M-Update-Tool'
$toolExecutable = Join-Path $toolDirectory 'UniOneUpdateTool.exe'
if (!(Test-Path -LiteralPath $toolExecutable)) { throw "Update tool missing: $toolExecutable" }
$digest = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$defaultFirmware = Join-Path $toolDirectory 'uni_app_release_update.bin'
if ((Test-Path -LiteralPath $defaultFirmware) -and (Get-FileHash -LiteralPath $defaultFirmware -Algorithm SHA256).Hash.ToLowerInvariant() -eq $digest) { throw 'This is the update tool bundled default firmware, not the generated StyleCam project firmware.' }
$destination = Join-Path $VoiceToolRoot ('stylecam_update_' + $digest.Substring(0,12))
New-Item -ItemType Directory -Path $destination -Force | Out-Null
foreach ($item in (Get-ChildItem -LiteralPath $toolDirectory -File)) {
    if ($item.Extension -in @('.exe','.dll','.ocx','.ini')) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $destination $item.Name) -Force }
}
$preparedFirmware = Join-Path $destination 'uni_app_release_update.bin'
Copy-Item -LiteralPath $sourceFile.FullName -Destination $preparedFirmware -Force
if ((Get-FileHash -LiteralPath $preparedFirmware -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) { throw 'Prepared firmware copy did not match its source.' }
$record = [ordered]@{source=$sourceFile.FullName;sha256=$digest;bytes=$sourceFile.Length;project_words_verified=$false;device_accessed=$false;note='Filename, nonempty content and copy SHA checked. The actual voice rules still require runtime acceptance.'}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination 'prepared_firmware.json') -Encoding UTF8
Write-Output "Prepared a separate update-tool folder using your generated firmware: $destination"
Write-Output "Open: $(Join-Path $destination 'UniOneUpdateTool.exe')"
Write-Output "Choose and verify firmware path: $preparedFirmware"
Write-Output 'No tool was launched, no serial port opened and no device programmed.'
