import streamlit as st
import pandas as pd
import requests
import time
import re
from datetime import datetime

# --- 1. 基础配置与 API ---
st.set_page_config(page_title="2026 聚合监控终端", layout="wide")
st.title("⚖️ 跨平台活跃市场监控 (全量扫描/自动聚合版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心逻辑：地毯式穷尽抓取 ---
def fetch_all_markets():
    poly_db = {}
    prob_db = {}
    status = st.sidebar.empty()

    # A. 抓取 Polymarket (扫描前 10 页，覆盖 1000 个市场)
    for i in range(10):
        status.text(f"读取 Polymarket 第 {i+1} 页...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            for m in r:
                title = m.get('question', '').strip()
                if title:
                    poly_db[title] = float(m.get('best_yes_price', 0))
            time.sleep(0.1) # 频率保护
        except: break

    # B. 抓取 Probable (扫描前 10 页)
    for i in range(1, 11):
        status.text(f"读取 Probable 第 {i} 页...")
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            r = requests.get(url, timeout=10).json()
            markets = r.get('markets', [])
            if not markets: break
            for m in markets:
                title = m.get('question', '').strip()
                if title:
                    prob_db[title] = float(m.get('yes_price', 0))
        except: break

    status.success("全量数据同步完成！")
    return poly_db, prob_db

# --- 3. 智能分组逻辑：识别“子选项”并聚合 ---
def group_matches(poly_db, prob_db, keyword):
    # 首先找出标题完全一致的市场
    common_titles = set(poly_db.keys()).intersection(set(prob_db.keys()))
    
    # 提取公共前缀作为“事件”名称 (例如将 >$2B 和 >$6B 归为一组)
    def get_event_stem(title):
        # 匹配包含 >$ 或具体数值的后缀并剔除，提取主干
        stem = re.sub(r'(\s[><]\$?\d+\w*\b|\s\d+\w*\b)(?=[^?]*\?)', ' [数值]', title)
        return stem

    groups = {}
    for title in common_titles:
        if keyword and keyword.lower() not in title.lower():
            continue
            
        stem = get_event_stem(title)
        if stem not in groups: groups[stem] = []
        
        groups[stem].append({
            "完整标题": title,
            "Polymarket 价格": f"${poly_db[title]:.3f}",
            "Probable 价格": f"${prob_db[title]:.3f}",
            "实时价差": round(abs(poly_db[title] - prob_db[title]), 4)
        })
    
    return groups

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 监控配置")
kw = st.sidebar.text_input("搜索关键词 (如 MegaETH)", "")
if st.sidebar.button("🚀 启动地毯式全量扫描"):
    st.write(f"⏰ **同步时间: {datetime.now().strftime('%H:%M:%S')}**")
    
    p_db, b_db = fetch_all_markets()
    grouped_results = group_matches(p_db, b_db, kw)
    
    if grouped_results:
        # 按事件主干排序
        sorted_stems = sorted(grouped_results.keys())
        
        for stem in sorted_parents:
            # 渲染聚合后的事件组
            with st.expander(f"📦 事件组：{stem.replace(' [数值]', ' ...')}", expanded=True):
                df = pd.DataFrame(grouped_results[stem])
                # 只保留名称差异部分作为展示，避免视觉冗余
                st.table(df)
    else:
        st.warning("地毯式扫描已完成，但未发现标题一致的市场。请检查关键词。")
