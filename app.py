import streamlit as st
import pandas as pd
import requests
import time
from fuzzywuzzy import fuzz

st.set_page_config(page_title="2026 跨平台对冲神器", layout="wide")
st.title("🛡️ Polymarket & Probable 真实数据监控")

# --- 1. 获取 Polymarket 活跃市场 (基于 image_e2ff5d) ---
def fetch_poly():
    try:
        url = "https://gamma-api.polymarket.com/markets?active=true&limit=100"
        resp = requests.get(url, timeout=10).json() # Polymarket 是列表
        return [{
            "title": m['question'],
            "liquidity": float(m.get('liquidity', 0)),
            "volume": float(m.get('volume', 0)),
            "tokens": m.get('clobTokenIds', [])
        } for m in resp if m.get('question')]
    except: return []

# --- 2. 获取 Probable 活跃市场 (基于 image_e2fc97) ---
def fetch_prob():
    try:
        url = "https://market-api.probable.markets/public/api/v1/markets/?active=true&limit=100"
        resp = requests.get(url, timeout=10).json()
        markets = resp.get('markets', []) # Probable 嵌套在 markets 键下
        return [{
            "title": m['question'],
            "liquidity": float(m.get('liquidity', 0)),
            "volume": float(m.get('volume24hr', 0)), # 对应截图字段
            "tokens": m.get('clobTokenIds', [])
        } for m in markets if m.get('question')]
    except: return []

# --- 3. 核心匹配逻辑 (降低精度，增加模糊度) ---
def analyze(fuzz_score):
    poly = fetch_poly()
    prob = fetch_prob()
    
    # 调试信息：显示在网页上，方便您确认是否抓到了标题
    st.sidebar.write(f"Poly 市场总数: {len(poly)}")
    st.sidebar.write(f"Prob 市场总数: {len(prob)}")
    
    matches = []
    for p in poly:
        for b in prob:
            # 标题模糊匹配
            score = fuzz.token_set_ratio(p['title'], b['title'])
            if score >= fuzz_score:
                matches.append({
                    "Poly 标题": p['title'],
                    "Prob 标题": b['title'],
                    "匹配度": score,
                    "深度(Poly)": p['liquidity'],
                    "深度(Prob)": b['liquidity'],
                    "总交易量": p['volume'] + b['volume']
                })
    return pd.DataFrame(matches)

# --- 4. 网页界面 ---
st.sidebar.header("调优参数")
fuzz_val = st.sidebar.slider("标题匹配精度 (建议 65-80)", 50, 95, 70)

placeholder = st.empty()
while True:
    df = analyze(fuzz_val)
    with placeholder.container():
        if not df.empty:
            # 排序：深度优先
            df_sorted = df.sort_values(by="深度(Poly)", ascending=False)
            st.success(f"成功匹配到 {len(df_sorted)} 个共同市场！")
            st.dataframe(df_sorted, use_container_width=True)
        else:
            st.info("正在深度扫描两个平台的市场，请稍候...")
    time.sleep(30)
    st.rerun()
