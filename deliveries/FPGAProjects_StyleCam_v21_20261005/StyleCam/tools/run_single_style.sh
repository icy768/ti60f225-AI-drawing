#!/usr/bin/env bash
# 单风格对照实验（并行两组）：A 损失同主模型；B 加 Gram 纹理损失
cd "$(dirname "$0")/../algo" || exit 1
PY=../.venv/Scripts/python.exe
COMMON="--styles mosaic --C 24 --n_res 4 --block dw1 --norm in --iters 8000 --workers 3"
PYTHONIOENCODING=utf-8 $PY -W ignore train.py $COMMON --out runs/mosaic_a > ../runs/mosaic_a.txt 2>&1 &
PYTHONIOENCODING=utf-8 $PY -W ignore train.py $COMMON --w_gram 2000 --out runs/mosaic_b > ../runs/mosaic_b.txt 2>&1 &
wait
for r in mosaic_a mosaic_b; do
    PYTHONIOENCODING=utf-8 $PY -W ignore eval.py --run runs/$r --n 40 --grid 3 > ../runs/$r/eval.txt 2>&1
done
echo done
