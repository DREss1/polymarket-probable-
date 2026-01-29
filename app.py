import streamlit as st
import pandas as pd
import requests
import time
import re
from datetime import datetime

st.set_page_config(page_title="2026 全量标题匹配", layout="wide")
st.title("⚖️ 跨平台“相同标题”地毯式监控")

# --- 1. 标题脱水工具：去除空格、特殊符号、统一大小写 ---
def normalize_title(text):
    if not text: return ""
    # 去除所有非字母数字字符，仅保留核心语义
    clean = re.sub(r'[^a-zA-Z0-9]', '', text).lower()
    return clean

# --- 2. 穷尽式抓取活跃市场 ---
def fetch_all_active_exhaustive():
    poly_list = []
    prob_list = []
    
    # A. 抓取 Polymarket (扫描前 5 页，确保覆盖 500 个市场)
    for i in range(5):
        url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            resp = requests.get(url, timeout=10).json()
            if not resp: break
            for m in resp:
                title = m.get('question', '').strip()
                poly_list.append({
                    "raw_title": title,
                    "norm_title": normalize_title(title),
                    "price": float(m.get('best_yes_price', 0)),
                    "url": f"https://polymarket.com/event/{m.get('slug')}"
                })
        except: break

    # B. 抓取 Probable (扫描前 5 页)
    for i in range(1, 6):
        url = f"https://market-api.probable.markets/public/api/v1/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            resp = requests.get(url, timeout=10).json()
            markets = resp.get('markets', [])
            if not markets: break
            for m in markets:
                title = m.get('question', '').strip()
                prob_list.append({
                    "raw_title": title,
                    "norm_title": normalize_title(title),
                    "price": float(m.get('yes_price', 0)),
                    "url": f"https://probable.markets/markets/{m.get('market_slug')}?id={m.get('id')}"
                })
        except: break
        
    return poly_list, prob_list

# --- 3. 匹配、排序与渲染 ---
def run_scan(keyword):
    p_data, b_data = fetch_all_active_exhaustive()
    
    # 建立 Probable 的索引
    b_map = {m['norm_title']: m for m in b_data}
    
    results = []
    for p in p_data:
        # 只要脱水后的标题一致，即视为相同市场
        if p['norm_title'] in b_map:
            b = b_map[p['norm_title']]
            
            # 关键词二次过滤
            if keyword and keyword.lower() not in p['raw_title'].lower():
                continue
                
            results.append({
                "市场标题": p['raw_title'],
                "Polymarket 价格": f"${p['price']:.3f}",
                "Probable 价格": f"${b['price']:.3f}",
                "差价": round(abs(p['price'] - b['price']), 4),
                "Poly 直达": p['url'],
                "Prob 直达": b['url']
            })
            
    df = pd.DataFrame(results)
    if not df.empty:
        # 按标题排序 [需求 2]
        df = df.sort_values(by="市场标题")
    return df

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 实时搜索配置")
kw = st.sidebar.text_input("标题关键词过滤", "")
refresh = st.sidebar.button("立即刷新")

placeholder = st.empty()

if refresh or "init" not in st.session_state:
    st.session_state.init = True
    df_final = run_scan(kw)
    with placeholder.container():
        st.write(f"⏰ 同步时间: {datetime.now().strftime('%H:%M:%S')}")
        if not df_final.empty:
            st.success(f"成功找出 {len(df_final)} 个相同市场")
            st.dataframe(
                df_final,
                column_config={
                    "Poly 直达": st.column_config.LinkColumn("交易"),
                    "Prob 直达": st.column_config.LinkColumn("交易")
                },
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("地毯式扫描完成，但未发现标题完全一致的市场。请检查关键词。")
