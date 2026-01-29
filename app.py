import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API 终点 ---
st.set_page_config(page_title="2026 标题对冲监控", layout="wide")
st.title("⚖️ 跨平台活跃市场标题监控 (地毯式扫描版)")

# 平台 API 地址
POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心抓取：地毯式全量翻页 (确保找回所有失踪市场) ---
def fetch_exhaustive_data():
    poly_all = []
    prob_all = []
    
    status_msg = st.sidebar.empty()
    
    # A. 抓取 Polymarket (扫描 500 个市场以确保覆盖面)
    for i in range(5):
        status_msg.text(f"正在读取 Polymarket 第 {i+1} 页...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            # 提取原始标题与价格
            for m in r:
                poly_all.append({
                    "raw_title": m['question'].strip(),
                    "price": float(m.get('best_yes_price', 0))
                })
            time.sleep(0.1) # 频率保护
        except: break

    # B. 抓取 Probable (扫描 500 个市场)
    for i in range(1, 6):
        status_msg.text(f"正在读取 Probable 第 {i} 页...")
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            r = requests.get(url, timeout=10).json()
            markets = r.get('markets', [])
            if not markets: break
            for m in markets:
                prob_all.append({
                    "raw_title": m['question'].strip(),
                    "price": float(m.get('yes_price', 0))
                })
        except: break
        
    status_msg.success(f"同步完成！共发现 Poly: {len(poly_all)} | Prob: {len(prob_all)}")
    return poly_all, prob_all

# --- 3. 匹配与排序逻辑 ---
def get_final_matches(keyword):
    poly_raw, prob_raw = fetch_exhaustive_data()
    
    # 建立字典：{标题: 价格}
    prob_map = {m['raw_title']: m['price'] for m in prob_raw}
    
    results = []
    for p in poly_raw:
        title = p['raw_title']
        
        # 关键词过滤
        if keyword and keyword.lower() not in title.lower():
            continue
            
        # 严格标题一致匹配
        if title in prob_map:
            results.append({
                "📋 市场标题 (点击下方单元格即可复制)": title,
                "Polymarket 价格": f"${p['price']:.3f}",
                "Probable 价格": f"${prob_map[title]:.3f}",
                "实时价差": round(abs(p['price'] - prob_map[title]), 4)
            })
            
    df = pd.DataFrame(results)
    # 需求：对名字一样且正在活跃的市场进行排序
    if not df.empty:
        df = df.sort_values(by="📋 市场标题 (点击下方单元格即可复制)")
    return df

# --- 4. 界面渲染 ---
st.sidebar.header("⚙️ 监控配置")
kw = st.sidebar.text_input("标题关键词搜索", "")
if st.sidebar.button("🚀 开启全量实时扫描"):
    data_df = get_final_matches(kw)
    
    st.write(f"⏰ **最后同步时间: {datetime.now().strftime('%H:%M:%S')}**")
    
    if not data_df.empty:
        st.info("💡 **一键复制技巧**：鼠标点击下表中任何标题，单元格右侧会出现一个小复制图标，点击即可。")
        # 渲染表格：移除所有链接列，仅保留标题和价格
        st.dataframe(
            data_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("⚠️ 地毯式扫描已完成，未发现标题完全一致的活跃市场。请检查关键词或稍后再试。")
