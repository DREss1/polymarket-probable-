import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from fuzzywuzzy import fuzz

st.set_page_config(page_title="2026 跨平台刷量助手 - 实战版", layout="wide")
st.title("🛡️ Polymarket & Probable 实时监控 (真实数据)")

# --- 1. 获取 Polymarket 数据 ---
def fetch_polymarket():
    try:
        url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50"
        resp = requests.get(url, timeout=10).json()
        return [{
            "title": m['question'],
            "poly_yes": float(m['best_yes_price']),
            "poly_no": 1 - float(m['best_yes_price']),
            "liquidity": float(m['liquidity']),
            "volume": float(m.get('volume', 0)),
            "end_date": m.get('end_date', '')[:10]
        } for m in resp if m.get('best_yes_price')]
    except: return []

# --- 2. 获取 Probable 真实数据 (基于文档截图) ---
def fetch_probable():
    try:
        base_url = "https://market-api.probable.markets/public/api/v1"
        # 获取市场列表
        markets_resp = requests.get(f"{base_url}/markets/?active=true&limit=20").json()
        markets = markets_resp.get('markets', []) # 文档显示字段为 markets
        
        # 准备批量价格查询的 Payload
        price_payload = []
        token_map = {} # 建立 token_id 与市场的映射
        for m in markets:
            if 'clobTokenIds' in m and len(m['clobTokenIds']) >= 2:
                yes_token = m['clobTokenIds'][0]
                no_token = m['clobTokenIds'][1]
                price_payload.append({"token_id": yes_token, "side": "BUY"}) # 获取 Yes 买价
                price_payload.append({"token_id": no_token, "side": "BUY"})  # 获取 No 买价
                token_map[yes_token] = (m['question'], 'yes')
                token_map[no_token] = (m['question'], 'no')

        # 批量获取价格
        price_resp = requests.post(f"{base_url}/prices", json=price_payload).json()
        
        # 整合数据
        processed = {}
        for m in markets:
            q = m['question']
            processed[q] = {
                "title": q, 
                "prob_yes": 0.5, "prob_no": 0.5, 
                "liquidity": float(m.get('liquidity', 0)),
                "volume": float(m.get('volume', 0))
            }
        
        for token_id, prices in price_resp.items():
            if token_id in token_map:
                q, side = token_map[token_id]
                processed[q][f"prob_{side}"] = float(prices.get('BUY', 0.5))

        return list(processed.values())
    except Exception as e:
        # st.error(f"Probable 接口异常: {e}")
        return []

# --- 3. 监控主循环 ---
st.sidebar.header("过滤参数")
cost_limit = st.sidebar.slider("对冲成本上限 (1.00 为绝对无损)", 0.95, 1.05, 1.02)

placeholder = st.empty()

while True:
    poly = fetch_polymarket()
    prob = fetch_probable()
    
    results = []
    if poly and prob:
        for p in poly:
            for b in prob:
                if fuzz.token_set_ratio(p['title'], b['title']) > 85:
                    # 方案 1: Poly 买 Yes + Prob 买 No (用价格计算)
                    cost_a = p['poly_yes'] + (1 - b['prob_yes']) # 基于文档价格逻辑推算
                    # 方案 2: Poly 买 No + Prob 买 Yes
                    cost_b = p['poly_no'] + b['prob_yes']
                    best_cost = min(cost_a, cost_b)
                    
                    if best_cost <= cost_limit:
                        results.append({
                            "市场名称": p['title'],
                            "刷量总成本": round(best_cost, 4),
                            "深度($)": round(min(p['liquidity'], b['liquidity']), 2),
                            "24h成交量": round(p['volume'] + b['volume'], 2),
                            "结算日期": p['end_date']
                        })

    with placeholder.container():
        st.write(f"⏰ 数据实时更新中: {datetime.now().strftime('%H:%M:%S')}")
        if results:
            df = pd.DataFrame(results).sort_values(by=['深度($)', '24h成交量'], ascending=False)
            st.dataframe(df.style.highlight_between(left=0.98, right=1.01, subset=['刷量总成本'], color='#D4EDDA'), use_container_width=True)
            if any(df['刷量总成本'] < 1.0): st.balloons()
        else:
            st.info("正在持续扫描跨平台套利机会...")

    time.sleep(30)
    st.rerun()
