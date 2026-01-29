import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API 终点 ---
st.set_page_config(page_title="2026 相同标题市场扫描器", layout="wide")
st.title("⚖️ 跨平台“相同标题”市场实时对冲监控")

# 平台 API 地址
POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心抓取逻辑：寻找正在活跃的市场 ---
def fetch_active_markets():
    """
    抓取两个平台所有状态为 active 且未结算的市场
    """
    poly_std = []
    prob_std = []

    # A. 抓取 Polymarket 活跃市场
    try:
        # 使用 active=true 和 closed=false 过滤
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100"
        r = requests.get(url, timeout=10).json()
        for m in r:
            poly_std.append({
                "标题": m.get('question', '').strip(),
                "Poly价格": float(m.get('best_yes_price', 0)),
                "链接": f"https://polymarket.com/event/{m.get('slug')}"
            })
    except: pass

    # B. 抓取 Probable 活跃市场
    try:
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100"
        r = requests.get(url, timeout=10).json()
        for m in r.get('markets', []):
            prob_std.append({
                "标题": m.get('question', '').strip(),
                "Prob价格": float(m.get('yes_price', 0)),
                "链接": f"https://probable.markets/markets/{m.get('market_slug')}?id={m.get('id')}"
            })
    except: pass

    return poly_std, prob_std

# --- 3. 匹配与排序逻辑 ---
def get_matched_df(keyword):
    p_markets, b_markets = fetch_active_markets()
    
    # 转换为字典，以标题为键，方便快速匹配
    p_dict = {m['标题']: m for m in p_markets}
    b_dict = {m['标题']: m for m in b_markets}

    matched_results = []

    # 寻找标题完全一致的市场
    for title, p_data in p_dict.items():
        if title in b_dict:
            b_data = b_dict[title]
            
            # 关键词过滤功能
            if keyword and keyword.lower() not in title.lower():
                continue
                
            matched_results.append({
                "市场标题": title,
                "Polymarket 实时价": f"${p_data['Poly价格']:.3f}",
                "Probable 实时价": f"${b_data['Prob价格']:.3f}",
                "价差": round(abs(p_data['Poly价格'] - b_data['Prob价格']), 4),
                "Poly直达": p_data['链接'],
                "Prob直达": b_data['链接']
            })

    # 将结果转换为 DataFrame 并按标题排序 [针对需求 2]
    df = pd.DataFrame(matched_results)
    if not df.empty:
        df = df.sort_values(by="市场标题", ascending=True)
    return df

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 搜索配置")
search_kw = st.sidebar.text_input("输入标题关键词", "")
refresh_sec = st.sidebar.slider("自动刷新周期 (秒)", 30, 300, 60)

status = st.empty()
table = st.empty()

while True:
    with status:
        st.write(f"🔄 正在同步全量活跃市场... 当前时间: {datetime.now().strftime('%H:%M:%S')}")
    
    df_final = get_matched_df(search_kw)
    
    with table.container():
        if not df_final.empty:
            st.success(f"✅ 成功找到 {len(df_final)} 个标题完全相同的活跃市场")
            st.dataframe(
                df_final,
                column_config={
                    "Poly直达": st.column_config.LinkColumn("交易链接"),
                    "Prob直达": st.column_config.LinkColumn("交易链接")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("⚠️ 目前未在两平台发现标题完全一致的活跃市场，请尝试更换关键词。")

    time.sleep(refresh_sec)
    st.rerun()
