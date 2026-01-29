import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime

# --- 基础配置与限速参数 ---
st.set_page_config(page_title="2026 跨平台全量监控", layout="wide")
st.title("🏹 跨平台“全量扫描”盈利统计系统")

# 根据 image_e28360 设定的 Polymarket 安全限速
POLY_RATE_LIMIT = 20  # 每秒请求数，远低于 30/s 的上限
# 根据 image_e27c99 设定的 Probable 缓存时间
PROB_CACHE_TIME = 180  # 3分钟刷新一次全量列表

# --- 1. 全量抓取逻辑 (Polymarket) ---
def fetch_all_poly():
    all_data = []
    offset = 0
    # 模拟分页直到抓完所有活跃市场
    while offset < 2000: # 设定一个上限
        url = f"https://gamma-api.polymarket.com/markets?active=true&limit=100&offset={offset}"
        try:
            resp = requests.get(url, timeout=5).json()
            if not resp: break
            all_data.extend(resp)
            offset += 100
            time.sleep(1 / POLY_RATE_LIMIT) # 严格遵守限速
        except: break
    return all_data

# --- 2. 全量抓取逻辑 (Probable - 基于 image_e36594 分页逻辑) ---
def fetch_all_prob():
    all_data = []
    base_url = "https://market-api.probable.markets/public/api/v1/markets/"
    try:
        # 第一页获取 totalResults
        first = requests.get(f"{base_url}?active=true&limit=100&page=1").json()
        total_results = first.get('pagination', {}).get('totalResults', 0)
        all_data.extend(first.get('markets', []))
        
        total_pages = (total_results // 100) + 1
        st.sidebar.success(f"Probable 检测到全量市场: {total_results}")

        def fetch_page(p):
            r = requests.get(f"{base_url}?active=true&limit=100&page={p}").json()
            return r.get('markets', [])

        with ThreadPoolExecutor(max_workers=5) as exec:
            results = list(exec.map(fetch_page, range(2, total_pages + 1)))
        for r in results: all_data.extend(r)
    except: pass
    return all_data

# --- 3. 核心盈利计算逻辑 ---
def analyze_full_market(keyword, fuzz_score):
    poly_raw = fetch_all_poly()
    prob_raw = fetch_all_prob()
    
    # 格式化数据并关键词预过滤
    poly_list = [{"title": m['question'], "yes": float(m.get('best_yes_price', 0.5)), "liq": float(m.get('liquidity', 0))} 
                 for m in poly_raw if m.get('question')]
    prob_list = [{"title": m['question'], "yes": float(m.get('yes_price', 0.5)), "liq": float(m.get('liquidity', 0))} 
                 for m in prob_raw if m.get('question')]

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
            
            # 盈利公式：$Cost = P_{poly\_yes} + P_{prob\_no}$
            # 其中 $P_{prob\_no} = 1 - P_{prob\_yes}$
            cost = p['yes'] + (1 - b['yes'])
            profit_pct = (1 - cost) * 100 if cost < 1 else (cost - 1) * -100
            
            matches.append({
                "市场名称": p['title'],
                "匹配度": best[1],
                "对冲总成本": round(cost, 4),
                "盈利空间": f"{profit_pct:.2f}%",
                "Poly深度 ($)": p['liq'],
                "Prob深度 ($)": b['liq'],
                "数据源": "2026 实时接口"
            })
    return pd.DataFrame(matches)

# --- 4. 界面渲染 ---
st.sidebar.header("对冲控制台")
kw = st.sidebar.text_input("聚焦关键词 (如 BTC/ETH)", "BTC")
f_score = st.sidebar.slider("标题对齐精度", 40, 95, 65)

placeholder = st.empty()
while True:
    start_time = time.time()
    df = analyze_full_market(kw, f_score)
    duration = time.time() - start_time
    
    with placeholder.container():
        st.write(f"⏱️ 全量对齐耗时: {duration:.2f} 秒 | 策略状态: **全量地毯式扫描中**")
        if not df.empty:
            # 高亮盈利机会 (成本 < 1.0)
            df_sorted = df.sort_values(by="对冲总成本", ascending=True)
            st.dataframe(df_sorted.style.highlight_between(left=0.90, right=1.00, subset=['对冲总成本'], color='#D4EDDA'), use_container_width=True)
            
            # 自动统计
            top_profit = df_sorted.iloc[0]['盈利空间']
            if "-" not in top_profit:
                st.success(f"🔥 当前最大盈利机会: {top_profit}")
                st.balloons()
        else:
            st.warning("全量扫描完成，暂未发现匹配机会。建议调低精度或更换关键词。")

    # 根据 Probable 缓存建议：每 3 分钟更新一次全量列表
    st.info(f"🔄 根据平台缓存政策，系统将在 {PROB_CACHE_TIME} 秒后进行下一轮全量同步。")
    time.sleep(PROB_CACHE_TIME)
    st.rerun()
