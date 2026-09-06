# 竞彩历史数据批量下载 (Windows PowerShell)
# 在挂VPN的本地PowerShell运行：.\download_history.ps1
# 下载完成后，将 downloads 文件夹打包为 zip 上传

New-Item -ItemType Directory -Force -Path downloads | Out-Null
Set-Location downloads

$cross = @(
  @{div="E1";code="E1";season="2627"},
  @{div="E2";code="E2";season="2627"},
  @{div="E3";code="E3";season="2627"},
  @{div="EC";code="EC";season="2627"},
  @{div="D1";code="D1";season="2627"},
  @{div="D2";code="D2";season="2627"},
  @{div="I1";code="I1";season="2627"},
  @{div="I2";code="I2";season="2627"},
  @{div="SP2";code="SP2";season="2627"},
  @{div="F2";code="F2";season="2627"},
  @{div="N1";code="N";season="2627"},
  @{div="B1";code="B1";season="2627"},
  @{div="P1";code="P1";season="2627"},
  @{div="SC0";code="SC0";season="2627"},
  @{div="SC1";code="SC1";season="2627"},
  @{div="SC2";code="SC2";season="2627"},
  @{div="SC3";code="SC3";season="2627"},
  @{div="T1";code="T1";season="2627"},
  @{div="G1";code="G1";season="2627"},
  @{div="PL";code="PL";season="2627"},
  @{div="AUT";code="AUT";season="2627"},
  @{div="ROU";code="ROU";season="2627"},
  @{div="RUS";code="RUS";season="2627"}
)

$calendar = @(
  @{div="ARG";code="ARG";season="2526"},
  @{div="BRA";code="BRA";season="2526"},
  @{div="CHN";code="CHN";season="2526"},
  @{div="FIN";code="FIN";season="2526"},
  @{div="IRL";code="IRL";season="2526"},
  @{div="JPN";code="JPN";season="2526"},
  @{div="MEX";code="MEX";season="2526"},
  @{div="NOR";code="NOR";season="2526"},
  @{div="SWE";code="SWE";season="2526"},
  @{div="USA";code="USA";season="2526"}
)

Write-Host "=== 下载跨年度联赛 2627 ==="
foreach ($item in $cross) {
  $url = "https://www.football-data.co.uk/mmz4281/$($item.season)/$($item.code).csv"
  $out = "$($item.div)_$($item.season).csv"
  Write-Host "  $($item.div) ($($item.season))"
  try {
    Invoke-WebRequest -Uri $url -OutFile $out -TimeoutSec 30 -UseBasicParsing
    $lines = (Get-Content $out).Count
    Write-Host "    OK $lines 行"
  } catch {
    Write-Host "    失败: $_"
  }
}

Write-Host ""
Write-Host "=== 下载自然年联赛 2526 ==="
foreach ($item in $calendar) {
  $url = "https://www.football-data.co.uk/mmz4281/$($item.season)/$($item.code).csv"
  $out = "$($item.div)_$($item.season).csv"
  Write-Host "  $($item.div) ($($item.season))"
  try {
    Invoke-WebRequest -Uri $url -OutFile $out -TimeoutSec 60 -UseBasicParsing
    $lines = (Get-Content $out).Count
    Write-Host "    OK $lines 行"
  } catch {
    Write-Host "    失败: $_"
  }
}

Write-Host ""
Write-Host "=== 完成 ==="
$count = (Get-ChildItem *.csv).Count
Write-Host "下载了 $count 个文件，在 downloads 文件夹"
Write-Host "请将 downloads 文件夹打包为 zip 上传"
