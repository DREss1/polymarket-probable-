import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime

# --- 1. 基础配置 ---
st.set_page_config(page_title="2026 全量监控-稳定版", layout="wide")
st.title("🏹 跨平台全量对冲监控 (稳定版)")

# 侧边栏配置：先渲染，避免白屏
st.sidebar.header("🎯 扫描配置")
kw = st.sidebar.text_input("关键词过滤 (如 BTC)", "BTC")
f_val = st.sidebar.slider("对齐精度", 40, 95, 70)
slip_val = st.sidebar.slider("允许滑点 (%)", 0.1, 5.0, 1.0)

# --- 2. 增强型抓取函数 ---
def fetch_poly_exhaustive():
    all_data = []
    offset = 0
    # 限制最大扫描 1500 个，平衡速度与深度
    while offset < 1500:
        url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={offset}"
        try:
            resp = requests.get(url, timeout=10).json()
            if not resp: break
            # 过滤掉已结算或无深度的僵尸市场
            valid = [m for m in resp if float(m.get('liquidity', 0)) > 100]
            all_data.extend(valid)
            offset += 100
            time.sleep(0.1) # 频率保护
        except: break
    return all_data

def fetch_prob_exhaustive():
    try:
        url = "https://market-api.probable.markets/public/api/v1/markets/?active=true&closed=false&limit=100"
        resp = requests.get(url, timeout=10).json()
        # Probable 数据在 markets 键下
        return [m for m in resp.get('markets', []) if float(m.get('liquidity', 0)) > 50]
    except: return []

# --- 3. 核心计算逻辑 ---
def get_analysis():
    # 使用 Spinner 解决白屏焦虑
    with st.spinner('正在同步全球预测市场全量数据...'):
        poly_raw = fetch_poly_exhaustive()
        prob_raw = fetch_prob_exhaustive()
        
        if not poly_raw or not prob_raw:
            return pd.DataFrame()

        # 标准化字段
        p_list = [{"title": m['question'], "yes": float(m.get('best_yes_price', 0.5)), 
                   "slug": m.get('slug'), "liq": float(m.get('liquidity', 0))} for m in poly_raw]
        b_list = [{"title": m['question'], "yes": float(m.get('yes_price', 0.5)), 
                   "slug": m.get('market_slug'), "liq": float(m.get('liquidity', 0))} for m in prob_raw]

        if kw:
            p_list = [m for m in p_list if kw.lower() in m['title'].lower()]
            b_list = [m for m in b_list if kw.lower() in m['title'].lower()]

        results = []
        b_titles = [m['title'] for m in b_list]
        for p in p_list:
            if not b_titles: break
            best = process.extractOne(p['title'], b_titles, scorer=fuzz.token_set_ratio)
            if best and best[1] >= f_val:
                b = b_list[best[2]]
                cost = p['yes'] + (1 - b['yes'])
                results.append({
                    "市场": p['title'],
                    "成本": round(cost, 4),
                    "收益率": f"{(1-cost)*100:.2f}%",
                    "Poly深度": f"${p['liq']:,.0f}",
                    "去Poly": f"https://polymarket.com/event/{p['slug']}",
                    "去Prob": f"https://probable.markets/markets/{b['slug']}"
                })
        return pd.DataFrame(results)

# --- 4. 运行与刷新 ---
placeholder = st.empty()
while True:
    df = get_analysis()
    with placeholder.container():
        if not df.empty:
            st.success(f"同步完成！检测到 {len(df)} 个潜在对冲机会")
            st.dataframe(
                df.style.highlight_between(left=0.95, right=1.0, subset=['成本'], color='#D4EDDA'),
                column_config={
                    "去Poly": st.column_config.LinkColumn("交易"),
                    "去Prob": st.column_config.LinkColumn("交易")
                }, use_container_width=True, hide_index=True
            )
        else:
            st.warning("当前筛选条件下未发现活跃对冲机会，请尝试更换关键词。")
    
    time.sleep(180) # 配合 Probable 3分钟缓存政策
    st.rerun()
