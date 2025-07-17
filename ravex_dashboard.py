import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import altair as alt
import os

# ========== CONFIG ==========
CSV_PATH = "ravex_signals_v27.csv"
RESULT_SAVE_PATH = "ravex_result_logs.csv"
BINANCE_API = "https://fapi.binance.com"
TP_RATIO = 0.03
SL_RATIO = 0.015

# ========== UTIL ==========
def get_latest_price(symbol):
    try:
        url = f"{BINANCE_API}/fapi/v1/ticker/price?symbol={symbol}"
        res = requests.get(url, timeout=3)
        res.raise_for_status()
        return float(res.json()['price'])
    except:
        return None

def evaluate_signal(row):
    symbol = row['symbol']
    entry_price = float(row['entry_price'])
    position = row['type']
    current_price = get_latest_price(symbol)

    if current_price is None:
        return entry_price, 0.0, 'NO_DATA'

    if position == 'BUY':
        roi = (current_price - entry_price) / entry_price
        result = 'TP_HIT' if roi >= TP_RATIO else 'SL_HIT' if roi <= -SL_RATIO else 'HOLD'
    elif position == 'SELL':
        roi = (entry_price - current_price) / entry_price
        result = 'TP_HIT' if roi >= TP_RATIO else 'SL_HIT' if roi <= -SL_RATIO else 'HOLD'
    else:
        roi = 0.0
        result = 'UNKNOWN'

    return current_price, roi, result

def save_to_csv(df, path):
    try:
        df.to_csv(path, index=False)
    except Exception as e:
        st.warning(f"⚠️ CSV 저장 실패: {e}")

# ========== MAIN DASHBOARD ==========
def launch_backtest(csv_path):
    st.set_page_config(layout="wide")
    st.title("📊 Ravex 실전 TP/SL 백테스트 대시보드 v2.0")
    st.markdown("🚀 실시간 ROI 기반 | 고급 차트 | 자동 저장 | 실전 구조")

    try:
        raw_df = pd.read_csv(csv_path)
        df = raw_df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df[df['type'].isin(['BUY', 'SELL'])]
        df = df[df['timestamp'] < datetime.now() - timedelta(minutes=10)]
        df = df.sort_values(by='timestamp', ascending=False).head(200)

        if 'entry_price' not in df.columns:
            st.error("❌ 'entry_price' 컬럼이 없습니다.")
            return

        st.info(f"✅ 총 {len(df)}개 시그널 평가 중...")

        results = []
        for _, row in df.iterrows():
            current_price, roi, result = evaluate_signal(row)
            results.append({
                'timestamp': row['timestamp'],
                'symbol': row['symbol'],
                'type': row['type'],
                'entry_price': row['entry_price'],
                'current_price': current_price,
                'roi': roi,
                'result': result
            })

        result_df = pd.DataFrame(results)
        result_df['cumulative_roi'] = result_df['roi'].cumsum()

        # 🔒 CSV 저장
        save_to_csv(result_df, RESULT_SAVE_PATH)

        # ✅ 상단 메트릭
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📦 총 거래 수", len(result_df))
        col2.metric("🎯 TP 성공률", f"{(result_df['result'] == 'TP_HIT').mean() * 100:.2f}%")
        col3.metric("📈 누적 ROI", f"{result_df['roi'].sum() * 100:.2f}%")
        col4.metric("📊 평균 ROI", f"{result_df['roi'].mean() * 100:.2f}%")

        # ✅ 탭
        tab1, tab2 = st.tabs(["📊 전체 요약", "🔍 개별 분석"])

        with tab1:
            st.subheader("📈 누적 수익률 (Altair)")
            chart = alt.Chart(result_df).mark_line(point=True).encode(
                x='timestamp:T',
                y='cumulative_roi:Q',
                tooltip=['timestamp', 'cumulative_roi']
            ).properties(width=800, height=300)
            st.altair_chart(chart, use_container_width=True)

            st.subheader("📊 TP/SL 결과 분포")
            bar_data = result_df['result'].value_counts().reset_index()
            bar_data.columns = ['result', 'count']
            bar_chart = alt.Chart(bar_data).mark_bar().encode(
                x='result:N',
                y='count:Q',
                color='result:N'
            )
            st.altair_chart(bar_chart, use_container_width=True)

            st.subheader("🧾 최근 시그널 로그")
            st.dataframe(result_df.sort_values(by='timestamp', ascending=False).head(30))

        with tab2:
            st.subheader("🧬 개별 시그널 분석")
            selected_idx = st.selectbox("시그널 선택 (최근순)", result_df.index)

            if selected_idx is not None:
                row = result_df.loc[selected_idx]
                entry = row['entry_price']
                current = row['current_price']
                tp = entry * (1 + TP_RATIO) if row['type'] == 'BUY' else entry * (1 - TP_RATIO)
                sl = entry * (1 - SL_RATIO) if row['type'] == 'BUY' else entry * (1 + SL_RATIO)

                st.markdown(f"""
                - **종목:** `{row['symbol']}`
                - **포지션:** `{row['type']}`
                - **수익률:** `{row['roi']*100:.2f}%`
                - **결과:** `{row['result']}`
                """)

                compare_df = pd.DataFrame({'가격': [entry, tp, sl, current]}, index=['Entry', 'TP', 'SL', 'Now'])
                st.bar_chart(compare_df)

    except Exception as e:
        st.error(f"❌ 백테스트 중 오류 발생: {e}")

# ========== RUN ==========
if __name__ == "__main__":
    launch_backtest(CSV_PATH)
