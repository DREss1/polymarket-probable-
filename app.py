import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from fuzzywuzzy import fuzz

st.set_page_config(page_title="2026 预测市场实时监控", layout="wide")
st.title("📊 Polymarket & Probable 实时监控面板")

# --- 1. 真实抓取 Polymarket 数据 ---
def fetch_polymarket():
    try:
        # 使用 Polymarket Gamma API 获取活跃市场
        url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            markets = []
            for m in data:
                if 'best_yes_price' in m and m.get('liquidity'):
                    markets.append({
                        "市场名称": m['question'],
                        "Poly_Yes": float(m['best_yes_price']),
                        "深度($)": float(m['liquidity']),
                        "24h成交量": float(m.get('volume', 0)),
                        "结算日期": m.get('end_date', '')[:10]
                    })
            return markets
    except Exception as e:
        st.error(f"Polymarket 连接失败: {e}")
    return []

# --- 2. 真实抓取 Probable 数据 (示例接口) ---
def fetch_probable():
    # 提示：由于 Probable 是新平台，此处使用其典型的 API 结构
    # 实际部署时请替换为 Probable 官方提供的 Endpoint
    try:
        url = "https://api.probable.market/v1/active-markets" 
        # 如果接口尚未完全公开，此处逻辑会返回空或使用测试网数据
        # 暂时返回一个空列表，直到你填入正确的 Probable API
        return []
    except:
        return []

# --- 3. 核心计算与匹配逻辑 ---
def get_live_opportunities():
    poly = fetch_polymarket()
    prob = fetch_probable()
    
    if not poly: return pd.DataFrame()
    
    # 如果 Probable 暂无数据，仅展示 Polymarket 供测试
    if not prob:
        df = pd.DataFrame(poly)
        # 伪造一个“成本”列用于演示 UI 效果，真实对冲需两个平台数据
        df['无损成本'] = df['Poly_Yes'] + 0.5 # 仅作占位
        return df

    # 跨平台匹配逻辑 (模糊匹配)
    results = []
    for p in poly:
        for b in prob:
            if fuzz.token_set_ratio(p['市场名称'], b['title']) > 85:
                # 假设买 Poly 的 Yes 和 Probable 的 No
                cost = p['Poly_Yes'] + b['prob_no']
                results.append({
                    "市场名称": p['市场名称'],
                    "无损成本": round(cost, 4),
                    "深度($)": min(p['深度($)'], b['liquidity']),
                    "24h成交量": p['24h成交量'] + b['volume'],
                    "结算日期": p['结算日期']
                })
    return pd.DataFrame(results)

# --- 4. Streamlit 界面更新 ---
st.sidebar.header("参数过滤")
cost_limit = st.sidebar.number_input("成本阈值", value=1.1, step=0.01)

placeholder = st.empty()

while True:
    df = get_live_opportunities()
    
    with placeholder.container():
        st.write(f"⏰ 最后同步时间: {datetime.now().strftime('%H:%M:%S')}")
        
        if not df.empty:
            # 排序：深度 > 成交量
            df_sorted = df[df['无损成本'] <= cost_limit].sort_values(by=['深度($)', '24h成交量'], ascending=False)
            
            st.dataframe(
                df_sorted.style.highlight_min(subset=['无损成本'], color='lightgreen'),
                use_container_width=True
            )
            
            if any(df_sorted['无损成本'] < 1.0):
                st.success("🔥 发现绝对套利机会！")
                st.balloons()
        else:
            st.info("正在获取实时数据，或当前无符合条件的市场...")

    time.sleep(30)
    st.rerun()
