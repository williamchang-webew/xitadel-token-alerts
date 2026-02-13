# 솔라나 토큰 텔레그램 알림

솔라나 네트워크에서 발행된 토큰의 **가격 도달**, **가격 변동률**, **거래량** 조건이 충족되면 텔레그램으로 알림을 보냅니다.

## 기능

| 조건 | 설명 |
|------|------|
| **가격 이상** | 토큰 가격이 설정한 USD 이상이 되면 알림 |
| **가격 이하** | 토큰 가격이 설정한 USD 이하가 되면 알림 |
| **가격 변동률** | 24시간 대비 N% 이상 상승/하락 시 알림 |
| **24h 거래량** | 24시간 거래량(USD)이 N 이상이면 알림 |
| **5분 거래량** | 5분 거래량(USD)이 N 이상이면 알림 (급등/급락 감지) |

가격·거래량 데이터는 **DexScreener** API를 사용하며, API 키 없이 사용할 수 있습니다.

## 설치

```bash
cd solana-token-alerts
pip install -r requirements.txt
```

## 설정

### 1. 텔레그램 봇

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 검색 후 `/newbot` 으로 봇 생성
2. 발급받은 **토큰** 복사
3. 알림 받을 채팅방에서 봇을 추가한 뒤, 아무 메시지나 보내기
4. 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 접속 후 응답 JSON 에서 `"chat":{"id": 숫자}` 확인 → 이 숫자가 **채팅 ID**

### 2. 환경 변수

프로젝트 폴더에 `.env` 파일을 만들면 자동으로 읽습니다 (python-dotenv 사용):

```bash
copy .env.example .env
# .env 를 열어 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 입력
```

또는 터미널에서 직접 내보내기:

```bash
# Windows (PowerShell)
$env:TELEGRAM_BOT_TOKEN="봇_토큰"
$env:TELEGRAM_CHAT_ID="채팅_ID"
```

### 3. config.yaml

```bash
copy config.example.yaml config.yaml
```

`config.yaml` 에서 다음을 수정하세요.

- **token_mint**: 감시할 토큰의 Solana **Contract Address (Mint 주소)**  
  - DexScreener, Birdeye, Raydium 등에서 토큰 페이지에 나오는 주소
- **alerts**: 필요한 조건만 숫자로 넣고, 쓰지 않는 항목은 `null` 로 두기

예시:

```yaml
token_mint: "So11111111111111111111111111111111111111112"

alerts:
  price_above: 100           # $100 이상이면 알림
  price_below: 0.0001       # $0.0001 이하면 알림
  price_change_pct_24h: 15  # 24h 대비 ±15% 변동 시 알림
  volume_24h_min: 100000    # 24h 거래량 $100,000 이상 시 알림
  volume_5m_min: 50000       # 5분 거래량 $50,000 이상 시 알림

check_interval_seconds: 60   # 60초마다 체크
alert_cooldown_seconds: 300  # 같은 종류 알림은 5분에 한 번만
```

## 실행

### 로컬 (PC 켜 둔 상태)

환경 변수 설정 후:

```bash
python alert_monitor.py
```

Ctrl+C 로 종료할 때까지 주기적으로 API를 조회하고, 조건 충족 시 텔레그램으로 알림을 보냅니다.

---

### PC 없이 24시간 알림 (GitHub Actions, 무료)

PC를 켜 두지 않아도 **5분마다** GitHub에서 자동으로 체크해 알림을 보냅니다. 비용 없음.

#### 1. GitHub 저장소 만들기

1. [GitHub](https://github.com) 로그인 후 **New repository** 로 새 저장소 생성 (이름 예: `solana-token-alerts`)
2. **이 프로젝트 폴더 전체**를 그 저장소에 올립니다.  
   - 저장소 **루트**에 `alert_monitor.py`, `config.yaml`, `requirements.txt`, `.github` 폴더 등이 오도록 푸시하세요.  
   - `solana-token-alerts` 폴더 **안의 파일들**을 루트에 두려면:  
     `solana-token-alerts` 안에서 `git init` → 원격 추가 → 푸시하거나,  
     상위 폴더에서 `git init` 후 `solana-token-alerts` 내용만 복사해 새 폴더에서 푸시해도 됩니다.

#### 2. config.yaml 올리기

- `config.example.yaml` 을 복사해 `config.yaml` 로 만든 뒤, **token_mint**와 **alerts** 값을 본인 설정으로 수정합니다.
- `config.yaml` 은 저장소에 **커밋해서 올립니다**. (봇 토큰은 넣지 않음.)

#### 3. 텔레그램 비밀값 등록

저장소 페이지에서 **Settings → Secrets and variables → Actions** 로 이동 후:

- **New repository secret** 로 아래 두 개 추가:
  - 이름: `TELEGRAM_BOT_TOKEN` → 값: 봇 토큰
  - 이름: `TELEGRAM_CHAT_ID` → 값: 채팅 ID

`.env` 파일은 **저장소에 올리지 마세요** (이미 `.gitignore`에 있음). GitHub Secrets 만 사용합니다.

#### 4. 동작 확인

- **Actions** 탭에서 **Solana Token Alert** 워크플로우가 보이면, **Run workflow** 로 한 번 수동 실행해 보세요.
- 정상이면 약 5분마다 자동 실행되며, 조건 충족 시 텔레그램으로 알림이 옵니다.
- 쿨다운(같은 알림 반복 방지)은 GitHub 캐시로 실행 간에 유지됩니다.

#### 요약

| 항목 | 설명 |
|------|------|
| 실행 주기 | 5분마다 (cron) |
| 비용 | 무료 (GitHub Actions 무료 할당량) |
| PC | 필요 없음 |
| 비밀 정보 | `.env` 대신 **Settings → Secrets** 에만 등록 |

## 참고

- **Mint 주소**: Solana 토큰의 고유 주소. Raydium, Jupiter, DexScreener 토큰 페이지에서 확인 가능
- **유동성**: 여러 DEX 페어가 있으면 유동성(USD)이 가장 큰 Solana 페어 하나를 기준으로 가격/거래량을 사용합니다
