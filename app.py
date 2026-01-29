import streamlit as st
import pandas as pd
import requests
import time
import re
from datetime import datetime

st.set_page_config(page_title="2026 全量标题对冲", layout="wide")
st.title("🌐 跨平台“全量市场”标题对冲监控")

# --- 1. 标题脱水工具：消除空格、标点和大小写干扰 ---
def clean_title(text):
    if not text: return ""
    # 只保留字母、数字和中文字符，统一小写
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', text).lower()

# --- 2. 穷尽式抓取活跃市场 ---
def fetch_everything():
    poly_all = []
    prob_all = []
    
    # 进度提示
    status = st.sidebar.empty()
    
    # A. 穷尽抓取 Polymarket (基于 offset 翻页)
    offset = 0
    while offset < 2000: # 扫描前 2000 个活跃市场
        status.text(f"正在扫描 Poly 第 {offset//100 + 1} 页...")
        url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={offset}"
        try:
            resp = requests.get(url, timeout=10).json()
            if not resp or len(resp) == 0: break
            poly_all.extend(resp)
            offset += 100
            time.sleep(0.1) # 频率保护
        except: break

    # B. 穷尽抓取 Probable (基于 page 翻页)
    page = 1
    while page <= 10: # 扫描前 1000 个市场
        status.text(f"正在扫描 Prob 第 {page} 页...")
        url = f"https://market-api.probable.markets/public/api/v1/markets/?active=true&closed=false&limit=100&page={page}"
        try:
            resp = requests.get(url, timeout=10).json()
            markets = resp.get('markets', [])
            if not markets: break
            prob_all.extend(markets)
            page += 1
        except: break
    
    status.success(f"同步完成！Poly: {len(poly_all)} | Prob: {len(prob_all)}")
    return poly_all, prob_all

# --- 3. 匹配与排序主逻辑 ---
def get_final_data(keyword):
    poly_raw, prob_raw = fetch_everything()
    
    # 建立 Prob 字典：{脱水标题: 原始数据}
    prob_map = {clean_title(m['question']): m for m in prob_raw}
    
    results = []
    for p in poly_raw:
        p_title_raw = p.get('question', '')
        p_title_clean = clean_title(p_title_raw)
        
        # 关键词过滤
        if keyword and keyword.lower() not in p_title_raw.lower():
            continue
            
        # 核心匹配：只要脱水标题一致就抓出来
        if p_title_clean in prob_map:
            b = prob_map[p_title_clean]
            
            p_price = float(p.get('best_yes_price', 0))
            b_price = float(b.get('yes_price', 0))
            
            results.append({
                "市场标题": p_title_raw,
                "Polymarket 价格": f"${p_price:.3f}",
                "Probable 价格": f"${b_price:.3f}",
                "对冲价差": round(abs(p_price - b_price), 4),
                "Poly 链接": f"https://polymarket.com/event/{p['slug']}",
                "Prob 链接": f"https://probable.markets/markets/{b['market_slug']}?id={b['id']}"
            })
    
    df = pd.DataFrame(results)
    if not df.empty:
        # 需求 2：按名字排序
        df = df.sort_values(by="市场标题")
    return df

# --- 4. 界面渲染 ---
st.sidebar.header("🎯 搜索与过滤")
kw = st.sidebar.text_input("标题关键词搜索 (如 BTC)", "")

if st.sidebar.button("🚀 开始全量地毯式同步"):
    df_final = get_final_data(kw)
    if not df_final.empty:
        st.success(f"✅ 深度扫描完成！在数千个市场中成功匹配到 {len(df_final)} 个相同标题市场。")
        st.dataframe(
            df_final,
            column_config={
                "Poly 链接": st.column_config.LinkColumn("交易"),
                "Prob 链接": st.column_config.LinkColumn("交易")
            },
            use_container_width=True, hide_index=True
        )
    else:
        st.warning("未发现完全一致的市场，请确保关键词准确或尝试调低匹配门槛。")
