import streamlit as st
import pandas as pd
import requests
import time
import re
from datetime import datetime

# --- 1. 基础配置与 API ---
st.set_page_config(page_title="2026 聚合监控终端", layout="wide")
st.title("⚖️ 跨平台活跃市场监控 (全量扫描/聚合对比版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心抓取：地毯式穷尽抓取 (覆盖 1000+ 市场) ---
def fetch_all_markets():
    poly_db = {}
    prob_db = {}
    status = st.sidebar.empty()

    # A. 抓取 Polymarket (扫描 10 页，确保找回失踪市场)
    for i in range(10):
        status.text(f"读取 Polymarket 第 {i+1} 页...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            for m in r:
                title = m.get('question', '').strip()
                if title:
                    # 记录价格与 slug (用于辅助识别)
                    poly_db[title] = float(m.get('best_yes_price', 0))
            time.sleep(0.1) 
        except: break

    # B. 抓取 Probable (同步扫描 10 页)
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

# --- 3. 智能聚合逻辑：将 >$2B, >$6B 等归入同一个父事件 ---
def group_matches(poly_db, prob_db, keyword):
    # 找出标题完全一致的市场
    common_titles = set(poly_db.keys()).intersection(set(prob_db.keys()))
    
    # 提取公共主干：去除标题末尾的数值和符号，用于分组
    def get_event_stem(title):
        # 匹配诸如 >$2B, >6B, 80,000 等数值后缀并替换，提取核心语义
        stem = re.sub(r'([><]?\$?\d+[\d,.]*\w*)\b', '[数值]', title)
        return stem

    groups = {}
    for title in common_titles:
        # 关键词过滤
        if keyword and keyword.lower() not in title.lower():
            continue
            
        stem = get_event_stem(title)
        if stem not in groups: groups[stem] = []
        
        # 识别该选项具体是什么（如 >$2B）
        option_detail = title.replace(stem.replace('[数值]', ''), '').strip()
        if not option_detail: option_detail = "主选项"

        groups[stem].append({
            "选项详情": title, # 这里保留完整标题以便你查阅
            "Polymarket 价格": f"${poly_db[title]:.3f}",
            "Probable 价格": f"${prob_db[title]:.3f}",
            "实时价差": round(abs(poly_db[title] - prob_db[title]), 4)
        })
    
    return groups

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 监控配置")
kw = st.sidebar.text_input("搜索关键词 (如 MegaETH)", "")
if st.sidebar.button("🚀 启动全量聚合扫描"):
    st.write(f"⏰ **数据同步时间: {datetime.now().strftime('%H:%M:%S')}**")
    
    p_db, b_db = fetch_all_markets()
    grouped_results = group_matches(p_db, b_db, kw)
    
    if grouped_results:
        # 修正后的变量名：sorted_stems
        sorted_stems = sorted(grouped_results.keys())
        
        for stem in sorted_stems: # 确保这里与定义的变量名一致
            # 渲染聚合折叠框
            display_name = stem.replace('[数值]', '...')
            with st.expander(f"📦 聚合事件：{display_name}", expanded=True):
                # 将该组下的所有选项转为表格
                df = pd.DataFrame(grouped_results[stem]).sort_values(by="选项详情")
                st.table(df)
    else:
        st.warning("地毯式扫描已完成，但未发现标题完全一致的对冲市场。")
