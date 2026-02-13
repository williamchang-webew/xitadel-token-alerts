# GitHub에 올리고 5분마다 알림 받기
# 1) 아래 "할 일" 먼저 한 뒤
# 2) 이 스크립트 실행 시 저장소 주소 입력

$repoUrl = Read-Host "GitHub 저장소 주소 입력 (예: https://github.com/내아이디/solana-token-alerts.git)"
if ([string]::IsNullOrWhiteSpace($repoUrl)) { exit 1 }

git remote remove origin 2>$null
git remote add origin $repoUrl
git branch -M main
git push -u origin main

Write-Host "`n푸시 완료. Actions 탭에서 워크플로 한 번 수동 실행해 보세요."
