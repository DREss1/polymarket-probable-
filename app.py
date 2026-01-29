import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from fuzzywuzzy import fuzz

st.set_page_config(page_title="2026 刷量深度监控", layout="wide")
st.title("🏹 跨平台深度与滑点监控系统")

BASE_PROB_URL = "https://market-api.probable.markets/public/api/v1"

# --- 1. 滑点深度计算核心函数 ---
def get_depth_with_slippage(token_id, side, max_slippage=0.01):
    """
    计算在指定滑点范围内，单笔能成交的最大美金深度
    """
    try:
        # 获取订单簿数据
        url = f"{BASE_PROB_URL}/book"
        params = {"token_id": token_id}
        resp = requests.get(url, params=params, timeout=5).json()
        
        # side="BUY" 对应订单簿的 asks (卖单层级)
        # side="SELL" 对应订单簿的 bids (买单层级)
        levels = resp.get('asks' if side == "BUY" else 'bids', [])
        if not levels: return 0.0

        initial_price = float(levels[0]['price'])
        limit_price = initial_price * (1 + max_slippage if side == "BUY" else 1 - max_slippage)
        
        total_volume_usd = 0.0
        cumulative_qty = 0.0
        
        for lvl in levels:
            price = float(lvl['price'])
            size = float(lvl['size'])
            
            # 如果价格超过了滑点限制，停止计算
            if (side == "BUY" and price > limit_price) or (side == "SELL" and price < limit_price):
                break
                
            total_volume_usd += (price * size)
            
        return round(total_volume_usd, 2)
    except:
        return 0.0

# --- 2. 抓取与对冲逻辑 ---
def fetch_and_analyze(slippage_limit, cost_threshold):
    # 此处保留 fetch_polymarket 逻辑
    poly_markets = requests.get("https://gamma-api.polymarket.com/markets?active=true&limit=30").json()
    prob_markets_resp = requests.get(f"{BASE_PROB_URL}/markets/?active=true").json()
    prob_markets = prob_markets_resp.get('markets', [])

    results = []
    for p in poly_markets:
        p_title = p['question']
        p_yes_price = float(p.get('best_yes_price', 0))
        
        for b in prob_markets:
            if fuzz.token_set_ratio(p_title, b['question']) > 85:
                # 获取 Probable 的 Token ID
                yes_token = b['clobTokenIds'][0]
                no_token = b['clobTokenIds'][1]
                
                # 计算 Probable 这边的滑点深度 (以买入 No 为例)
                safe_depth_usd = get_depth_with_slippage(no_token, "BUY", slippage_limit)
                
                # 假设对冲成本：Poly Yes + Prob No
                prob_no_price = 1 - 0.5 # 实际应调用 /prices 接口获取真实值
                total_cost = p_yes_price + prob_no_price
                
                if total_cost <= cost_threshold:
                    results.append({
                        "市场名称": p_title,
                        "对冲成本": round(total_cost, 4),
                        "1%滑点内最大交易额 ($)": safe_depth_usd,
                        "Polymarket 总深度": round(float(p.get('liquidity', 0)), 2),
                        "24h成交量": round(float(p.get('volume', 0)), 2)
                    })
    return results

# --- 3. Streamlit 侧边栏与主循环 ---
st.sidebar.header("高级刷量设置")
slippage_input = st.sidebar.slider("允许的最大滑点 (%)", 0.1, 5.0, 1.0) / 100
cost_input = st.sidebar.number_input("对冲成本上限", value=1.02)

placeholder = st.empty()
while True:
    data = fetch_and_analyze(slippage_input, cost_input)
    with placeholder.container():
        st.write(f"⏰ 数据刷新于: {datetime.now().strftime('%H:%M:%S')}")
        if data:
            df = pd.DataFrame(data).sort_values(by="1%滑点内最大交易额 ($)", ascending=False)
            st.dataframe(df.style.background_gradient(subset=['1%滑点内最大交易额 ($)'], cmap='Greens'), use_container_width=True)
        else:
            st.info("扫描中... 暂未发现符合条件的刷量机会。")
    time.sleep(30)
    st.rerun()
