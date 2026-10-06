#!/usr/bin/env bash
# 分段并行 + 断点续传下载 COCO val2017（单连接仅约 300KB/s）
URL=http://images.cocodataset.org/zips/val2017.zip
L=815585330
N=16
cd "$(dirname "$0")/../data" || exit 1
rm -f val2017.zip
P=$(( (L + N - 1) / N ))

fetch() {
  local i=$1 s=$(( $1 * P )) e=$(( ($1 + 1) * P - 1 ))
  [ $e -ge $L ] && e=$((L - 1))
  local f=part_$(printf %02d "$i") want=$(( e - s + 1 ))
  touch "$f"
  for try in $(seq 1 200); do
    local have
    have=$(stat -c %s "$f")
    [ "$have" -ge "$want" ] && return 0
    curl -sS --max-time 600 -r $(( s + have ))-$e "$URL" >> "$f"
  done
  return 1
}

for i in $(seq 0 $((N - 1))); do fetch "$i" & done
wait
for i in $(seq 0 $((N - 1))); do
  s=$(( i * P )); e=$(( (i + 1) * P - 1 )); [ $e -ge $L ] && e=$((L - 1))
  [ "$(stat -c %s part_$(printf %02d $i))" -eq $(( e - s + 1 )) ] || { echo "part $i 不完整"; exit 1; }
done
cat part_* > val2017.zip && rm part_*
unzip -q -o val2017.zip && ls val2017 | wc -l
