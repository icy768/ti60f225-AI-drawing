$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name | Format-Table -AutoSize
Write-Output 'This only lists Windows device information. No serial port was opened.'
