import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API ---
st.set_page_config(page_title="2026 标题对冲监控", layout="wide")
st.title("⚖️ 跨平台活跃市场标题监控 (已开启一键复制)")

# API 地址
POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心抓取：地毯式穷尽翻页 ---
def fetch_all_active():
    poly_list, prob_list = [], []
    
    status = st.sidebar.empty()
    
    # A. 抓取 Polymarket 全量活跃区 (基于 offset 翻页)
    for i in range(5): # 扫描前 500 个市场以确保覆盖
        status.text(f"正在扫描 Poly 第 {i+1} 页...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            # 提取标题与价格
            poly_list.extend([{"title": m['question'].strip(), "poly_price": m['best_yes_price']} for m in r])
            time.sleep(0.1) # 频率保护
        except: break

    # B. 抓取 Probable 全量活跃区 (基于 page 翻页)
    for i in range(1, 6): # 扫描前 500 个市场
        status.text(f"正在扫描 Prob 第 {i} 页...")
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            r = requests.get(url, timeout=10).json()
            markets = r.get('markets', [])
            if not markets: break
            # 提取标题与价格
            prob_list.extend([{"title": m['question'].strip(), "prob_price": m['yes_price']} for m in markets])
        except: break
        
    status.success(f"同步完成！共发现 Poly: {len(poly_list)} | Prob: {len(prob_list)}")
    return poly_list, prob_list

# --- 3. 匹配、排序与显示逻辑 ---
def get_matched_df(keyword):
    poly_raw, prob_raw = fetch_all_active()
    
    # 建立字典以快速匹配
    prob_map = {m['title']: m for m in prob_raw}
    
    results = []
    for p in poly_raw:
        title = p['title']
        # 关键词过滤
        if keyword and keyword.lower() not in title.lower():
            continue
            
        # 标题完全一致匹配
        if title in prob_map:
            b = prob_map[title]
            results.append({
                "📋 市场标题 (点击即可复制)": title,
                "Polymarket 价格": f"${float(p['poly_price']):.3f}",
                "Probable 价格": f"${float(b['prob_price']):.3f}",
                "实时价差": round(abs(float(p['poly_price']) - float(b['prob_price'])), 4)
            })
            
    df = pd.DataFrame(results)
    if not df.empty:
        # 按标题排序 [需求 2]
        df = df.sort_values(by="📋 市场标题 (点击即可复制)")
    return df

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 监控配置")
search_kw = st.sidebar.text_input("标题关键词过滤", "")
if st.sidebar.button("🚀 立即全量扫描"):
    df_final = get_matched_df(search_kw)
    
    st.write(f"📊 **匹配结果** | 最后更新: {datetime.now().strftime('%H:%M:%S')}")
    if not df_final.empty:
        st.info("💡 提示：点击下表中任意标题即可直接复制。")
        # 使用 st.dataframe 渲染，利用其内置的一键复制功能
        st.dataframe(
            df_final,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("地毯式扫描已完成，未发现标题完全一致的活跃市场。")
