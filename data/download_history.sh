#!/bin/bash
# 竞彩历史数据批量下载脚本
# 在挂VPN的本地环境运行：bash download_history.sh
# 下载完成后，将 downloads/ 目录打包为 zip 上传

mkdir -p downloads
cd downloads

# 跨年度联赛 2627赛季（23个，E0/SP1/F1已完成跳过）
declare -A CROSS=(
  [E1]=2627 [E2]=2627 [E3]=2627 [EC]=2627
  [D1]=2627 [D2]=2627 [I1]=2627 [I2]=2627
  [SP2]=2627 [F2]=2627 [N]=2627 [B1]=2627
  [P1]=2627 [SC0]=2627 [SC1]=2627 [SC2]=2627 [SC3]=2627
  [T1]=2627 [G1]=2627 [PL]=2627 [AUT]=2627 [ROU]=2627 [RUS]=2627
)

# 自然年联赛 2526赛季（10个）
declare -A CALENDAR=(
  [ARG]=2526 [BRA]=2526 [CHN]=2526 [FIN]=2526 [IRL]=2526
  [JPN]=2526 [MEX]=2526 [NOR]=2526 [SWE]=2526 [USA]=2526
)

echo "=== 下载跨年度联赛 2627 ==="
for code in "${!CROSS[@]}"; do
  season=${CROSS[$code]}
  url="https://www.football-data.co.uk/mmz4281/${season}/${code}.csv"
  # 荷甲本地Div是N1，下载URL用N
  div=$code
  [ "$code" = "N" ] && div="N1"
  out="${div}_${season}.csv"
  echo "  $div ($season): $url"
  curl -sL --max-time 30 -o "$out" "$url"
  if [ -f "$out" ] && [ -s "$out" ]; then
    lines=$(wc -l < "$out")
    echo "    ✅ $lines 行"
  else
    echo "    ❌ 失败"
  fi
done

echo ""
echo "=== 下载自然年联赛 2526 ==="
for code in "${!CALENDAR[@]}"; do
  season=${CALENDAR[$code]}
  url="https://www.football-data.co.uk/mmz4281/${season}/${code}.csv"
  out="${code}_${season}.csv"
  echo "  $code ($season): $url"
  curl -sL --max-time 60 -o "$out" "$url"
  if [ -f "$out" ] && [ -s "$out" ]; then
    lines=$(wc -l < "$out")
    echo "    ✅ $lines 行"
  else
    echo "    ❌ 失败"
  fi
done

echo ""
echo "=== 完成 ==="
echo "下载的文件在 downloads/ 目录，共 $(ls *.csv 2>/dev/null | wc -l) 个"
echo "请将 downloads/ 目录打包为 zip 上传"
