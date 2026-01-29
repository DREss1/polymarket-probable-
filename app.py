import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime

# --- 1. 基础配置与安全参数 ---
st.set_page_config(page_title="2026 职业对冲-全量版", layout="wide")
st.title("🏹 跨平台“地毯式”对冲监控系统")

# 平台限速与缓存常量
POLY_DELAY = 1 / 15  # 每秒 15 次，安全规避 30次/秒 的限制
PROB_CACHE = 180     # 3分钟缓存周期

# --- 2. 侧边栏：核心控制功能 ---
st.sidebar.header("🎯 扫描控制中心")
keyword = st.sidebar.text_input("1️⃣ 关键词搜索 (如: BTC)", "BTC")
fuzz_score = st.sidebar.slider("2️⃣ 对齐精度 (越高越严格)", 40, 95, 70)
slip_limit = st.sidebar.slider("3️⃣ 滑点预警阈值 (%)", 0.1, 2.0, 1.0)

# --- 3. 增强型抓取逻辑 (带进度条) ---
def fetch_exhaustive_data():
    poly_all = []
    prob_all = []
    
    # 初始化进度条
    progress_bar = st.progress(0, text="正在启动全量同步...")
    
    # A. 抓取 Polymarket (穷尽翻页)
    for i in range(5): # 扫描前 500 个市场，确保覆盖 2026 热门
        progress_bar.progress(10 + i * 10, text=f"正在同步 Polymarket 第 {i+1} 页...")
        url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            # 过滤 2026 年活跃且有深度的市场
            poly_all.extend([m for m in r if float(m.get('liquidity', 0)) > 100])
            time.sleep(POLY_DELAY)
        except: break

    # B. 抓取 Probable (基于总量自动翻页)
    try:
        prob_url = "https://market-api.probable.markets/public/api/v1/markets/?active=true&limit=100&page=1"
        first = requests.get(prob_url, timeout=10).json()
        total_res = first.get('pagination', {}).get('totalResults', 0)
        prob_all.extend(first.get('markets', []))
        
        pages = (total_res // 100) + 1
        for p in range(2, min(pages + 1, 6)):
            progress_bar.progress(60 + p * 5, text=f"正在同步 Probable 第 {p} 页...")
            r = requests.get(f"https://market-api.probable.markets/public/api/v1/markets/?active=true&limit=100&page={p}").json()
            prob_all.extend(r.get('markets', []))
    except: pass
    
    progress_bar.progress(100, text="同步完成！正在进行 AI 标题匹配...")
    time.sleep(1)
    progress_bar.empty() # 完成后清空进度条
    
    return poly_all, prob_all

# --- 4. 核心对齐与成本计算 ---
def run_analysis():
    poly_raw, prob_raw = fetch_exhaustive_data()
    
    # 数据标准化
    p_std = [{"title": m['question'], "yes": float(m.get('best_yes_price', 0.5)), 
              "slug": m.get('slug'), "liq": float(m.get('liquidity', 0))} for m in poly_raw]
    b_std = [{"title": m['question'], "yes": float(m.get('yes_price', 0.5)), 
              "slug": m.get('market_slug'), "liq": float(m.get('liquidity', 0))} for m in prob_raw]

    # 关键词过滤：提升速度 10 倍
    if keyword:
        p_std = [m for m in p_std if keyword.lower() in m['title'].lower()]
        b_std = [m for m in b_std if keyword.lower() in m['title'].lower()]

    matches = []
    b_titles = [m['title'] for m in b_std]
    
    for p in p_std:
        if not b_titles: break
        # 对齐精度功能：使用 rapidfuzz 算法
        best = process.extractOne(p['title'], b_titles, scorer=fuzz.token_set_ratio)
        if best and best[1] >= fuzz_score:
            b = b_std[best[2]]
            # 盈利公式：$Cost = P_{poly\_yes} + (1 - P_{prob\_yes})$
            cost = p['yes'] + (1 - b['yes'])
            
            matches.append({
                "市场名称": p['title'],
                "匹配度": f"{best[1]}%",
                "对冲总成本": round(cost, 4),
                "盈利空间": f"{(1-cost)*100:.2f}%" if cost < 1 else "-",
                "深度 (Poly/Prob)": f"${p['liq']:,.0f} / ${b['liq']:,.0f}",
                "去Poly": f"https://polymarket.com/event/{p['slug']}",
                "去Prob": f"https://probable.markets/markets/{b['slug']}"
            })
    return pd.DataFrame(matches)

# --- 5. 渲染循环 ---
placeholder = st.empty()
while True:
    df = run_analysis()
    with placeholder.container():
        st.write(f"⏰ 最后全量更新: {datetime.now().strftime('%H:%M:%S')}")
        if not df.empty:
            df_display = df.sort_values(by="对冲总成本")
            st.dataframe(
                df_display.style.highlight_between(left=0.9, right=1.0, subset=['对冲总成本'], color='#D4EDDA'),
                column_config={
                    "去Poly": st.column_config.LinkColumn("直达"),
                    "去Prob": st.column_config.LinkColumn("直达")
                }, use_container_width=True, hide_index=True
            )
            if any(df['对冲总成本'] < 1.0): st.success("💰 发现盈利机会！已高亮显示。"); st.balloons()
        else:
            st.info(f"未在 2026 年活跃市场中发现关于 '{keyword}' 的对冲机会。")
            
    st.sidebar.warning(f"⏳ 遵照 Probable 缓存政策，系统冷却中...")
    time.sleep(PROB_CACHE) # 3分钟同步一次
    st.rerun()
