import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone

# --- 1. 基础配置与 API 路径 ---
st.set_page_config(page_title="2026 精准对冲系统", layout="wide")
st.title("🏹 跨平台 ID 级精准监控系统 (2026 稳定版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心逻辑：获取实时深度 ---
def get_depth_and_price(token_id, platform="poly"):
    """
    实时抓取订单簿并计算 1% 滑点内的深度
    """
    try:
        if platform == "poly":
            url = f"{POLY_CLOB}/book?token_id={token_id}"
        else:
            url = f"{PROB_API}/book?token_id={token_id}"
            
        r = requests.get(url, timeout=3).json()
        # 刷量买入时对应卖单 (asks)
        levels = r.get('asks', [])
        if not levels: return 0.5, 0.0
        
        best_price = float(levels[0]['price'])
        limit = best_price * 1.01 # 锁定 1% 滑点深度
        total_usd = sum(float(l['price']) * float(l['size']) for l in levels if float(l['price']) <= limit)
        return best_price, round(total_usd, 2)
    except:
        return 0.5, 0.0

# --- 3. 核心对齐引擎：ID 级映射 ---
def sync_markets_by_id(keyword):
    # 初始化进度条
    prog = st.progress(0, text="同步 Polymarket 活跃市场中...")
    
    # A. 抓取 Poly 实时活跃区 (过滤 2020-2024 幽灵数据)
    poly_map = {}
    try:
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100"
        resp = requests.get(url, timeout=10).json()
        for m in resp:
            c_id = m.get('conditionId')
            # 物理屏蔽历史年份 slug
            if c_id and "2020" not in m['slug'] and "2024" not in m['slug']:
                poly_map[c_id] = m
    except: pass

    prog.progress(50, text="正在通过 ID 映射 Probable 相同市场...")
    
    # B. 抓取 Probable 实时活跃区并与 Poly 对齐
    matches = []
    try:
        prob_url = f"{PROB_API}/markets/?active=true&limit=100"
        p_resp = requests.get(prob_url, timeout=10).json().get('markets', [])
        
        for b in p_resp:
            b_cid = b.get('condition_id') # 获取 Probable 端的标识符
            if b_cid in poly_map:
                p = poly_map[b_cid]
                
                # 关键词过滤功能
                if keyword and keyword.lower() not in p['question'].lower(): continue
                
                # 实时深度抓取 (Token 1 通常是 'Yes')
                p_token = p['clobTokenIds'][0] if p.get('clobTokenIds') else ""
                b_token = b['clobTokenIds'][0] if b.get('clobTokenIds') else ""
                
                p_price, p_depth = get_depth_and_price(p_token, "poly")
                b_price, b_depth = get_depth_and_price(b_token, "prob")
                
                cost = p_price + (1 - b_price)
                
                matches.append({
                    "ID 对齐市场": p['question'],
                    "对冲成本": round(cost, 4),
                    "收益预期": f"{(1-cost)*100:.2f}%" if cost < 1 else "-",
                    "深度 (Poly/Prob)": f"${p_depth:,.0f} / ${b_depth:,.0f}",
                    "Poly 链接": f"https://polymarket.com/event/{p['slug']}",
                    "Prob 链接": f"https://probable.markets/markets/{b['market_slug']}?id={b['id']}"
                })
    except: pass
    
    prog.empty()
    return pd.DataFrame(matches)

# --- 4. 界面渲染 ---
st.sidebar.header("⚙️ 监控配置")
kw = st.sidebar.text_input("关键词搜索", "BTC")
refresh_time = st.sidebar.slider("刷新周期 (秒)", 60, 300, 180)

placeholder = st.empty()
while True:
    df = sync_markets_by_id(kw)
    with placeholder.container():
        st.write(f"✅ **ID 级同步完成** | 最后更新: {datetime.now().strftime('%H:%M:%S')}")
        if not df.empty:
            st.dataframe(
                df.style.highlight_between(left=0.0, right=1.0, subset=['对冲成本'], color='#D4EDDA'),
                column_config={
                    "Poly 链接": st.column_config.LinkColumn("直达"),
                    "Prob 链接": st.column_config.LinkColumn("直达")
                }, use_container_width=True, hide_index=True
            )
        else:
            st.info("当前搜索下未发现已对齐的活跃市场。")
            
    time.sleep(refresh_time)
    st.rerun()
