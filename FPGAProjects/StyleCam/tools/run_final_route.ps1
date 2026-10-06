param(
    [int]$Iters = 3000,
    [int]$Workers = 4,
    [switch]$QAT,
    [string]$BaseCheckpoint = 'runs/c24_dw1_in/student.pt'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = Join-Path (Split-Path (Split-Path (Get-Location) -Parent) -Parent) 'style_network\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "Python runtime not found: $py" }

$common = @(
    'algo/train.py', '--C', '24', '--Fc', '16', '--n_res', '4',
    '--block', 'dw1', '--norm', 'in', '--styles', 'candy,mosaic,rain_princess,udnie',
    '--iters', "$Iters", '--batch', '16', '--crop', '256', '--workers', "$Workers",
    '--camera_aug_prob', '0.75', '--temporal_weight', '0.005', '--temporal_shift', '1',
    '--w_gram', '0', '--seed', '20261003', '--lr', '0.0002',
    '--weights_only', $BaseCheckpoint, '--save_every', '500'
)
if ($QAT) {
    & $py @common '--qat_frac', '0.5' '--out', 'runs/final_route_camera_temporal_qat'
} else {
    & $py @common '--qat_frac', '1.0' '--out', 'runs/final_route_camera_temporal_fp32'
}
if ($LASTEXITCODE -ne 0) { throw "training failed with exit code $LASTEXITCODE" }
