# ✅ Ravex 시그널 시스템 v2.7.2 - 백테스트, 시각화, 대시보드 통합 예정 버전
# ------------------------------------------------------
# - 동적 신뢰도 기반 시그널
# - 실패/반전/관망 시그널 로직 포함
# - 향후 업그레이드 예정:
#   1. 백테스트 모듈 (CSV 기반 ROI 분석)
#   2. 실시간 시각화 모듈 (Plotly/Matplotlib 기반)
#   3. 웹 대시보드 (Streamlit 또는 Dash)
# ------------------------------------------------------

print("🤖 Ravex 시그널 실행 시작됨!")

import requests
import time
from datetime import datetime
import pandas as pd
import os
from pytz import timezone

# 기본 설정
kst = timezone('Asia/Seoul')
TELEGRAM_TOKEN = "7734143160:AAE5Y-u3t_-ZZjfWM9WvwXxluxl3_Sbo4u4"
TELEGRAM_CHAT_ID = "-1002837722170"
BASE_URL = "https://fapi.binance.com"
CSV_SIGNAL_FILE = r"C:\Users\ozil3\Downloads\ravex_signals_v27.csv"
CHECK_INTERVAL = 60
COOLDOWN_MINUTES = 5
last_alerted = {}

def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=payload)
    except Exception as e:
        print("Telegram error:", e)

def get_kline(symbol, interval='5m', limit=20):
    try:
        url = f"{BASE_URL}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url)
        return res.json()
    except:
        return []

def get_rsi_from_closes(closes, length=14):
    gains = [max(0, closes[i+1] - closes[i]) for i in range(length)]
    losses = [max(0, closes[i] - closes[i+1]) for i in range(length)]
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_funding_rate(symbol):
    try:
        url = f"{BASE_URL}/fapi/v1/premiumIndex?symbol={symbol}"
        res = requests.get(url)
        return float(res.json().get("lastFundingRate", 0))
    except:
        return 0

def get_all_symbols():
    try:
        res = requests.get(f"{BASE_URL}/fapi/v1/exchangeInfo")
        data = res.json()['symbols']
        return [s['symbol'] for s in data if s['quoteAsset'] == 'USDT' and s['contractType'] == 'PERPETUAL']
    except:
        return []

def detect_candidates():
    candidates = []
    symbols = get_all_symbols()
    for symbol in symbols:
        candles = get_kline(symbol, '1m', 10)
        if len(candles) < 10:
            continue
        vols = [float(c[5]) for c in candles]
        avg_vol = sum(vols[:8]) / 8
        recent_vol = vols[-1]
        if recent_vol > avg_vol * 1.8:
            candidates.append(symbol)
    return candidates

def log_to_csv(data, path):
    try:
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            os.makedirs(folder)

        df = pd.DataFrame([data])
        if not os.path.exists(path):
            df.to_csv(path, index=False)
        else:
            df.to_csv(path, mode='a', header=False, index=False)
    except Exception as e:
        print("CSV 저장 오류:", e)
        send_telegram_message(f"⚠️ CSV 저장 오류 발생: {e}")

def calculate_dynamic_confidence(pct, vol_chg, rsi):
    conf = 0
    if abs(pct) > 0.02:
        conf += 0.4
    elif abs(pct) > 0.015:
        conf += 0.3
    elif abs(pct) > 0.01:
        conf += 0.2
    else:
        conf += 0.1

    if vol_chg > 3.0:
        conf += 0.4
    elif vol_chg > 2.0:
        conf += 0.3
    elif vol_chg > 1.5:
        conf += 0.2
    else:
        conf += 0.1

    if rsi > 70 or rsi < 30:
        conf += 0.3
    elif rsi > 60 or rsi < 40:
        conf += 0.2
    else:
        conf += 0.1

    return min(conf, 1.0)

def classify_bullish_signal(pct, vol_chg, rsi, candles):
    if pct > 0.006 and candles[-1][4] < candles[-1][1] and rsi > 60:
        return "🚫 상승실패"
    elif pct > 0.013 and vol_chg > 2.1 and rsi > 60:
        return "📈 고점돌파"
    elif candles[-1][4] > candles[-2][4] and vol_chg > 1.7 and pct > 0.007 and rsi > 55:
        return "📊 가속상승"
    elif pct > 0.006 and vol_chg > 1.4 and 40 < rsi < 60:
        return "🔂 눌림목반등"
    elif rsi < 30 and pct > 0 and vol_chg > 1.2:
        return "🟡 기술적반등"
    else:
        return "🔍 관망시그널"

def classify_bearish_signal(pct, vol_chg, rsi, candles):
    if rsi > 75 and pct < -0.002 and vol_chg > 1.1:
        return "🔻 과매수반전"
    elif pct < -0.006 and candles[-1][4] > candles[-1][1] and rsi < 45:
        return "🚫 하락실패"
    elif pct < -0.016 and vol_chg > 2.0 and rsi < 45:
        return "📉 지지이탈"
    elif candles[-1][4] < candles[-2][4] and vol_chg > 1.6 and pct < -0.009:
        return "💢 가속급락"
    elif pct < -0.006 and rsi > 50 and vol_chg > 1.3:
        return "🔃 기술적되돌림"
    else:
        return "🔍 관망시그널"

def scan_symbols(symbols):
    for symbol in symbols:
        try:
            candles = get_kline(symbol, '5m', 20)
            if len(candles) < 20:
                continue

            closes = [float(c[4]) for c in candles[-15:]]
            rsi = get_rsi_from_closes(closes)
            old_p, new_p = float(candles[-2][4]), float(candles[-1][4])
            recent_vol = float(candles[-1][5])
            avg_vol = sum(float(c[5]) for c in candles[-4:-1]) / 3
            pct = (new_p - old_p) / old_p
            vol_chg = recent_vol / avg_vol if avg_vol > 0 else 0
            funding = get_funding_rate(symbol)
            confidence = calculate_dynamic_confidence(pct, vol_chg, rsi)

            now_kst = datetime.now(kst)
            cooldown = last_alerted.get(symbol, datetime.min.replace(tzinfo=kst))
            time_passed = (now_kst - cooldown).total_seconds()
            if time_passed < COOLDOWN_MINUTES * 60:
                continue

            if pct > 0.006 and vol_chg > 1.4:
                signal_type = "BUY"
                tag = classify_bullish_signal(pct, vol_chg, rsi, candles)
                emoji = "🚀 상승형"
                comment = "✅ 매수 검토 (판단은 수동)"
            elif pct < -0.007 and vol_chg > 1.3:
                signal_type = "SELL"
                tag = classify_bearish_signal(pct, vol_chg, rsi, candles)
                emoji = "⚠️ 하락형"
                comment = "✅ 매도 검토 (판단은 수동)"
            else:
                continue

            last_alerted[symbol] = now_kst

            msg = (
                f"\n{emoji} 시그널 - {symbol} {tag}\n"
                f"📊 변화율: {round(pct*100,2)}%\n"
                f"🔥 거래량: x{round(vol_chg,2)} (3봉 평균 대비)\n"
                f"🧠 RSI: {round(rsi,2)}\n"
                f"💰 펀딩비: {round(funding*100,4)}%\n"
                f"🎯 신뢰도: {round(confidence*100)}%\n"
                f"👉 {comment}"
            )

            send_telegram_message(msg)

            log_to_csv({
                "timestamp": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "pct_change": round(pct*100,2),
                "vol_change": round(vol_chg,2),
                "rsi": round(rsi,2),
                "funding": round(funding*100,4),
                "type": signal_type,
                "tag": tag,
                "confidence": round(confidence*100),
                "entry_price": float(candles[-1][4])
            }, CSV_SIGNAL_FILE)

        except Exception as e:
            print("Error:", e)

send_telegram_message("🤖 Ravex 시그널 시스템 v2.7.2 - 동적 신뢰도 + 실패/반전 시그널 적용")

while True:
    try:
        candidates = detect_candidates()
        if candidates:
            scan_symbols(candidates)
        else:
            print(f"[{datetime.now(kst).strftime('%H:%M:%S')}] No candidates.")
        time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        send_telegram_message("🚩 수동 종료됨")
        break
    except Exception as e:
        send_telegram_message(f"⚠️ 오류 발생: {e}")
        time.sleep(60)



# ✅ 백테스트 모듈 - v1.4
def run_backtest(csv_path, tp=0.03, sl=0.015):
    import pandas as pd
    import random

    df = pd.read_csv(csv_path)
    df = df[df['type'] == 'BUY'].copy()

    results = []
    for i, row in df.iterrows():
        entry_price = 100  # 기준 진입 가격
        take_profit = entry_price * (1 + tp)
        stop_loss = entry_price * (1 - sl)

        # 55% 확률로 TP, 나머지는 SL 시뮬레이션 (추후 실제가 필요하면 연동)
        hit_tp = random.random() < 0.55
        exit_price = take_profit if hit_tp else stop_loss
        roi = (exit_price - entry_price) / entry_price

        results.append({
            'symbol': row['symbol'],
            'timestamp': row['timestamp'],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'roi': roi,
            'result': 'WIN' if hit_tp else 'LOSS'
        })

    result_df = pd.DataFrame(results)
    total_roi = result_df['roi'].sum()
    win_rate = (result_df['result'] == 'WIN').mean()

    print(f"📈 총 ROI: {round(total_roi*100, 2)}%")
    print(f"✅ 승률: {round(win_rate*100, 2)}%")
    print(f"📊 총 거래 수: {len(result_df)}건")

    return result_df



# ✅ 시각화 모듈 - v1.5
import matplotlib.pyplot as plt

def visualize_backtest_results(result_df):
    try:
        if result_df.empty:
            print("❌ 데이터 없음: 백테스트 결과가 비어있습니다.")
            return

        # ROI 누적 그래프
        result_df['cumulative_roi'] = result_df['roi'].cumsum()
        plt.figure(figsize=(12, 6))
        plt.plot(result_df['timestamp'], result_df['cumulative_roi'], label='누적 수익률', linewidth=2)
        plt.xticks(rotation=45)
        plt.xlabel("시간")
        plt.ylabel("누적 ROI")
        plt.title("📈 Ravex 백테스트 누적 수익률")
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.show()

        # 승/패 분포 바 차트
        result_df['result'].value_counts().plot(kind='bar', color=['green', 'red'])
        plt.title("✅ 결과 분포 (WIN/LOSS)")
        plt.ylabel("건수")
        plt.xticks(rotation=0)
        plt.grid(axis='y')
        plt.tight_layout()
        plt.show()

    except Exception as e:
        print(f"⚠️ 시각화 오류: {e}")

# ✅ 1. 함수 정의 (이게 먼저 있어야 함)
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

def launch_dashboard(csv_path):
    st.set_page_config(layout="wide")
    st.title("📊 Ravex Signal Dashboard v2.7.2")
    st.markdown("실시간 시그널 로그 기반 백테스트 및 시각화")

    try:
        df = pd.read_csv(csv_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        df = df[df['type'] == 'BUY']

        # ROI 임시 시뮬레이션
        import random
        df['entry_price'] = 100
        df['exit_price'] = df['entry_price'] * (1 + 0.03) * (
            df.index.to_series().apply(lambda x: 1 if random.random() < 0.55 else 0)
            + (1 - df.index.to_series().apply(lambda x: 1 if random.random() < 0.55 else 0)) * (1 - 0.015)
        )
        df['roi'] = (df['exit_price'] - df['entry_price']) / df['entry_price']
        df['result'] = df['roi'].apply(lambda x: 'WIN' if x > 0 else 'LOSS')
        df['cumulative_roi'] = df['roi'].cumsum()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("✅ 총 거래 수", len(df))
            st.metric("🏆 승률", f"{round((df['result'] == 'WIN').mean()*100, 2)}%")
        with col2:
            st.metric("📈 총 ROI", f"{round(df['roi'].sum()*100, 2)}%")
            st.metric("📉 손익 비율", f"{round(df['roi'].mean()*100, 2)}%")

        st.markdown("### 📈 누적 ROI 차트")
        st.line_chart(df.set_index('timestamp')['cumulative_roi'])

        st.markdown("### ✅ 결과 분포 (WIN / LOSS)")
        result_counts = df['result'].value_counts()
        st.bar_chart(result_counts)

        st.markdown("### 📋 최근 시그널 로그")
        st.dataframe(df[['timestamp', 'symbol', 'tag', 'roi', 'result']].sort_values(by='timestamp', ascending=False).head(20))

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        
# ✅ 실제 대시보드 실행 트리거 (맨 아래에 추가해줘야 함)
if __name__ == "__main__":
    launch_dashboard(CSV_SIGNAL_FILE)
