param(
    [ValidateSet('usb_uart', 'native_usb')][string]$Variant = 'usb_uart',
    [string]$Port,
    [string]$ToolRoot,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
$entry = $manifest.variants.$Variant
if (-not $entry) { throw "Build variant missing: $Variant" }
foreach ($item in $entry.sha256.PSObject.Properties) {
    $target = Join-Path (Join-Path $PSScriptRoot $Variant) $item.Name
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $item.Value) { throw "SHA256 mismatch: $target" }
}
$image = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $Variant) -Filter '*.merged.bin'
if (@($image).Count -ne 1) { throw 'Expected exactly one merged image for flash address 0.' }
Write-Output "Verified $Variant : $($image.Name)"
if ($CheckOnly) {
    Write-Output 'CheckOnly passed. No serial port opened and no device programmed.'
    return
}
if (-not $Port -or -not $ToolRoot) { throw 'Specify -Port COMx and -ToolRoot <portable Arduino tools>; -CheckOnly is offline.' }
$toolDir = Join-Path $ToolRoot 'data/packages/esp32/tools/esptool_py/5.1.0-cn'
$esptool = @(Get-ChildItem -LiteralPath $toolDir -Filter esptool.exe -Recurse)
if ($esptool.Count -ne 1) { throw "Expected one esptool.exe below $toolDir" }
$esptoolPath = $esptool[0].FullName
& $esptoolPath --chip esp32s3 --port $Port --baud 460800 --before default-reset --after hard-reset write-flash 0x0 $image.FullName
if ($LASTEXITCODE -ne 0) { throw "ESP32 flashing failed: $LASTEXITCODE" }
