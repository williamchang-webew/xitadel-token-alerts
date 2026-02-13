#!/usr/bin/env python3
"""
솔라나 네트워크 토큰 가격/거래량 모니터링 후 텔레그램 알림.

- 특정 가격 도달 (이상/이하)
- N% 이상 가격 변동 (24h)
- N USD 이상 거래량 (24h 또는 5m)

로컬: python alert_monitor.py (무한 반복)
GitHub Actions: python alert_monitor.py --once (한 번만 실행 후 종료, 상태 파일로 쿨다운 유지)
"""

import argparse
import json
import os
import time
import logging
from pathlib import Path

import requests
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
STATE_PATH = SCRIPT_DIR / "alert_state.json"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"설정 파일이 없습니다: {CONFIG_PATH}\n"
            "config.example.yaml 을 config.yaml 로 복사한 뒤 수정하세요."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    """쿨다운용 마지막 알림 시각을 파일에서 읽음 (GitHub Actions 등에서 실행 간 유지)."""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("상태 파일 읽기 실패, 초기화: %s", e)
        return {}


def save_state(last_alert_time: dict) -> None:
    """마지막 알림 시각을 파일에 저장."""
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(last_alert_time, f, indent=0)
    except Exception as e:
        log.warning("상태 파일 저장 실패: %s", e)


def get_telegram_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit(
            "환경 변수가 필요합니다: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID\n"
            "텔레그램에서 @BotFather 로 봇을 만들고, 봇과 대화 후 채팅 ID를 확인하세요."
        )
    return token, chat_id


def send_telegram(text: str, token: str, chat_id: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        if not r.ok:
            log.warning("텔레그램 전송 실패: %s %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.warning("텔레그램 전송 예외: %s", e)
        return False


def fetch_token_data(mint: str):
    """DexScreener에서 토큰 정보 조회. Solana 체인 기준으로 유동성 높은 페어 우선 사용."""
    url = f"{DEXSCREENER_API}/{mint}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        log.warning("DexScreener 요청 실패: %s", e)
        return None
    except Exception as e:
        log.warning("응답 파싱 실패: %s", e)
        return None

    pairs = data.get("pairs") or []
    # Solana 체인만, 유동성 기준 정렬
    solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not solana_pairs:
        solana_pairs = pairs
    if not solana_pairs:
        log.warning("해당 토큰의 거래 페어를 찾을 수 없습니다.")
        return None

    def liquidity_key(p):
        return float(p.get("liquidity", {}).get("usd") or 0)

    best = max(solana_pairs, key=liquidity_key)
    base = best.get("baseToken") or {}
    return {
        "symbol": base.get("symbol", "?"),
        "name": base.get("name", "?"),
        "price_usd": float(best.get("priceUsd") or 0),
        "price_change_pct_24h": _float(best.get("priceChange", {}).get("h24")),
        "volume_24h": _float(best.get("volume", {}).get("h24")),
        "volume_5m": _float(best.get("volume", {}).get("m5")),
        "txns_24h_buys": ((best.get("txns") or {}).get("h24") or {}).get("buys") or 0,
        "txns_24h_sells": ((best.get("txns") or {}).get("h24") or {}).get("sells") or 0,
        "url": best.get("url", ""),
        "pair_address": best.get("pairAddress", ""),
    }


def _float(v):
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_once(config, token, chat_id, last_alert_time: dict):
    mint = config.get("token_mint")
    if not mint:
        log.error("config.yaml 에 token_mint 가 없습니다.")
        return

    alerts_cfg = config.get("alerts") or {}
    interval = config.get("check_interval_seconds", 60)
    cooldown = config.get("alert_cooldown_seconds", 300)
    now = time.time()

    data = fetch_token_data(mint)
    if not data:
        return

    price = data["price_usd"]
    change_24h = data["price_change_pct_24h"]
    vol_24h = data["volume_24h"]
    vol_5m = data["volume_5m"]
    symbol = data["symbol"]
    name = data["name"]
    url = data.get("url", "")

    def can_alert(alert_key):
        last = last_alert_time.get(alert_key, 0)
        return (now - last) >= cooldown

    def mark_alert(alert_key):
        last_alert_time[alert_key] = now

    messages = []

    def _to_list(v):
        if v is None:
            return []
        return [v] if isinstance(v, (int, float)) else list(v)

    # 가격 이상 (여러 구간 가능)
    for above in _to_list(alerts_cfg.get("price_above")):
        try:
            thresh = float(above)
        except (TypeError, ValueError):
            continue
        key = f"price_above_{thresh}"
        if price >= thresh and can_alert(key):
            messages.append(
                f"🔼 가격 도달\n{symbol} ({name})\n"
                f"현재 가격: ${price:.6g} (설정: ${thresh} 이상)"
            )
            mark_alert(key)

    # 가격 이하 (여러 구간 가능)
    for below in _to_list(alerts_cfg.get("price_below")):
        try:
            thresh = float(below)
        except (TypeError, ValueError):
            continue
        key = f"price_below_{thresh}"
        if price <= thresh and can_alert(key):
            messages.append(
                f"🔽 가격 하락\n{symbol} ({name})\n"
                f"현재 가격: ${price:.6g} (설정: ${thresh} 이하)"
            )
            mark_alert(key)

    # 24h 변동률
    change_pct = alerts_cfg.get("price_change_pct_24h")
    if change_pct is not None and change_24h != 0 and abs(change_24h) >= change_pct:
        key = "price_change_pct_24h"
        if can_alert(key):
            direction = "상승" if change_24h > 0 else "하락"
            messages.append(
                f"📊 24h 가격 변동\n{symbol} ({name})\n"
                f"현재 가격: ${price:.6g}\n"
                f"24h 변동: {change_24h:+.2f}% ({direction})"
            )
            mark_alert(key)

    # 24h 거래량
    vol_24h_min = alerts_cfg.get("volume_24h_min")
    if vol_24h_min is not None and vol_24h >= vol_24h_min and can_alert("volume_24h_min"):
        messages.append(
            f"📈 24h 거래량 돌파\n{symbol} ({name})\n"
            f"24h 거래량: ${vol_24h:,.0f} (설정: ${vol_24h_min:,.0f} 이상)\n"
            f"매수/매도 횟수: {data['txns_24h_buys']} / {data['txns_24h_sells']}"
        )
        mark_alert("volume_24h_min")

    # 5m 거래량
    vol_5m_min = alerts_cfg.get("volume_5m_min")
    if vol_5m_min is not None and vol_5m >= vol_5m_min and can_alert("volume_5m_min"):
        messages.append(
            f"⚡ 5분 거래량 급증\n{symbol} ({name})\n"
            f"5분 거래량: ${vol_5m:,.0f} (설정: ${vol_5m_min:,.0f} 이상)"
        )
        mark_alert("volume_5m_min")

    for msg in messages:
        if url:
            msg += f"\n\n{url}"
        if send_telegram(msg, token, chat_id):
            log.info("알림 발송: %s", msg[:80].replace("\n", " ") + "…" if len(msg) > 80 else msg[:80])


def main():
    parser = argparse.ArgumentParser(description="솔라나 토큰 가격/거래량 텔레그램 알림")
    parser.add_argument(
        "--once",
        action="store_true",
        help="한 번만 체크 후 종료 (GitHub Actions 등 스케줄 실행용)",
    )
    args = parser.parse_args()

    config = load_config()
    token, chat_id = get_telegram_credentials()
    last_alert_time = load_state()

    if args.once:
        log.info("한 번 실행 모드 (--once)")
        try:
            run_once(config, token, chat_id, last_alert_time)
        finally:
            save_state(last_alert_time)
        return

    log.info("솔라나 토큰 알림 모니터 시작 (종료: Ctrl+C)")
    while True:
        try:
            run_once(config, token, chat_id, last_alert_time)
            save_state(last_alert_time)
        except KeyboardInterrupt:
            log.info("종료합니다.")
            break
        except Exception as e:
            log.exception("한 번 실행 중 오류: %s", e)
        time.sleep(config.get("check_interval_seconds", 60))


if __name__ == "__main__":
    main()
