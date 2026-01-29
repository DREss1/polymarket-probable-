import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime

# --- 基础配置 ---
st.set_page_config(page_title="2026 极速对冲-直达版", layout="wide")
st.title("🎯 跨平台“一键直达”对冲监控系统")

POLY_RATE_LIMIT = 20 
PROB_CACHE_TIME = 180 

# --- 1. 获取 Poly 数据 (新增 slug) ---
def fetch_all_poly():
    all_data = []
    offset = 0
    while offset < 1000:
        # Polymarket 链接结构通常使用 slug
        url = f"https://gamma-api.polymarket.com/markets?active=true&limit=100&offset={offset}"
        try:
            resp = requests.get(url, timeout=5).json()
            if not resp: break
            all_data.extend(resp)
            offset += 100
            time.sleep(1 / POLY_RATE_LIMIT) 
        except: break
    return all_data

# --- 2. 获取 Prob 数据 (新增 market_slug) ---
def fetch_all_prob():
    all_data = []
    base_url = "https://market-api.probable.markets/public/api/v1/markets/"
    try:
        first = requests.get(f"{base_url}?active=true&limit=100&page=1").json()
        total_results = first.get('pagination', {}).get('totalResults', 0)
        all_data.extend(first.get('markets', []))
        
        total_pages = (total_results // 100) + 1
        def fetch_page(p):
            r = requests.get(f"{base_url}?active=true&limit=100&page={p}").json()
            return r.get('markets', []) # Probable 数据包裹在 markets 键下

        with ThreadPoolExecutor(max_workers=5) as exec:
            results = list(exec.map(fetch_page, range(2, total_pages + 1)))
        for r in results: all_data.extend(r)
    except: pass
    return all_data

# --- 3. 分析与链接拼装 ---
def analyze_with_links(keyword, fuzz_score):
    poly_raw = fetch_all_poly()
    prob_raw = fetch_all_prob()
    
    # 提取关键信息，包括用于拼装 URL 的 slug
    poly_list = [{
        "title": m['question'], 
        "yes": float(m.get('best_yes_price', 0.5)), 
        "liq": float(m.get('liquidity', 0)),
        "url": f"https://polymarket.com/event/{m.get('slug')}" # 拼装 Poly 链接
    } for m in poly_raw if m.get('question')]

    prob_list = [{
        "title": m['question'], 
        "yes": float(m.get('yes_price', 0.5)), 
        "liq": float(m.get('liquidity', 0)),
        "url": f"https://probable.markets/markets/{m.get('market_slug')}" # 拼装 Prob 链接
    } for m in prob_raw if m.get('question')]

    if keyword:
        poly_list = [m for m in poly_list if keyword.lower() in m['title'].lower()]
        prob_list = [m for m in prob_list if keyword.lower() in m['title'].lower()]

    matches = []
    prob_titles = [m['title'] for m in prob_list]
    for p in poly_list:
        if not prob_titles: break
        best = process.extractOne(p['title'], prob_titles, scorer=fuzz.token_set_ratio)
        if best and best[1] >= fuzz_score:
            b = prob_list[best[2]]
            cost = p['yes'] + (1 - b['yes'])
            matches.append({
                "市场名称": p['title'],
                "对冲总成本": round(cost, 4),
                "Poly 深度": f"${p['liq']:,.0f}",
                "Prob 深度": f"${b['liq']:,.0f}",
                "去 Poly 交易": p['url'],
                "去 Prob 交易": b['url']
            })
    return pd.DataFrame(matches)

# --- 4. 渲染界面 ---
st.sidebar.header("对冲面板")
kw = st.sidebar.text_input("关键词", "BTC")
f_score = st.sidebar.slider("对齐精度", 40, 95, 65)

placeholder = st.empty()
while True:
    df = analyze_with_links(kw, f_score)
    with placeholder.container():
        if not df.empty:
            st.write(f"⏰ 更新于: {datetime.now().strftime('%H:%M:%S')}")
            # 使用 Streamlit 的 LinkColumn 让链接可点击
            st.dataframe(
                df,
                column_config={
                    "去 Poly 交易": st.column_config.LinkColumn("前往 Polymarket"),
                    "去 Prob 交易": st.column_config.LinkColumn("前往 Probable")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("暂未发现机会，请保持关键词为空或调低精度。")
    time.sleep(PROB_CACHE_TIME)
    st.rerun()
