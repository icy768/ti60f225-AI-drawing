# StyleCam 一键回归：依次运行全部仿真与主机测试，逐项判定 PASS/FAIL
# 用法（工程根目录）：powershell -ExecutionPolicy Bypass -File tools\regress.ps1
# 判定：退出码为 0、输出含 PASS、且不含 FAIL；每项日志写到 sim\work\regress\<序号>.log
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root '.venv\Scripts\python.exe'
$logd = Join-Path $root 'sim\work\regress'
New-Item -ItemType Directory -Force $logd | Out-Null
New-Item -ItemType Directory -Force (Join-Path $root 'sw\test\work') | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:Path = 'C:\iverilog\bin;D:\mingw64\mingw64\bin;' + $env:Path

# 每项：名称、工作目录、命令
$steps = @(
    @{ n = 'swg3 滑窗（8 组）';                     d = 'sim';  c = { & $py run_swg3.py } },
    @{ n = 'cam_scale3 降采样';                     d = 'sim';  c = { & $py run_scale.py } },
    @{ n = 'motion_det 运动检测';                   d = 'sim';  c = { & $py run_motion.py } },
    @{ n = 'raw_bin3 SC431HAI 前端';                d = 'sim';  c = { & $py run_rawbin.py } },
    @{ n = 'raw_bin2 IMX219 前端（5 组）';          d = 'sim';  c = { & $py run_rawbin2.py } },
    @{ n = 'AE/AWB 闭环（7 场景）';                 d = 'sw';   c = { & gcc -O2 -I. test/isp_test.c isp.c -lm -o test/work/isp_test.exe; if ($LASTEXITCODE -eq 0) { & .\test\work\isp_test.exe } } },
    @{ n = '整网 NN 逐位（48x32，统计+权重装载）'; d = 'algo'; c = { & $py gen_rtl.py --W 48 --H 32 --stat_layer 5 --load_weights } },
    @{ n = '整链路 摄像头→DDR→NN→HDMI+OSD+APB';   d = 'sim';  c = { & $py run_sys.py } },
    @{ n = '固件 IN 刷新';                          d = 'algo'; c = { & $py test_fw.py } }
)

$res = @()
$i = 0
foreach ($s in $steps) {
    $i++
    Write-Host ("[{0}/{1}] {2} ..." -f $i, $steps.Count, $s.n)
    Push-Location (Join-Path $root $s.d)
    $t0 = Get-Date
    $global:LASTEXITCODE = 0
    $out = (& $s.c 2>&1 | ForEach-Object { "$_" }) -join "`n"
    $code = $LASTEXITCODE
    Pop-Location
    $sec = [int]((Get-Date) - $t0).TotalSeconds
    $logf = Join-Path $logd ("{0:D2}.log" -f $i)
    [IO.File]::WriteAllText($logf, $out, [Text.Encoding]::UTF8)
    $ok = ($code -eq 0) -and ($out -match 'PASS') -and ($out -notmatch 'FAIL')
    $res += [pscustomobject]@{ '#' = $i; '项目' = $s.n; '结果' = $(if ($ok) { 'PASS' } else { 'FAIL' }); '秒' = $sec; '日志' = $logf.Substring($root.Length + 1) }
    Write-Host ("      {0}（{1} 秒）" -f $(if ($ok) { 'PASS' } else { "FAIL，退出码 $code，见 $logf" }), $sec)
}
$res | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$nfail = @($res | Where-Object { $_.'结果' -ne 'PASS' }).Count
Write-Host ("合计 {0} 项，PASS {1}，FAIL {2}" -f $res.Count, ($res.Count - $nfail), $nfail)
exit $(if ($nfail) { 1 } else { 0 })
