import streamlit as st
import pandas as pd
import requests
import time
from rapidfuzz import fuzz, process
from datetime import datetime, timezone

# --- 1. 基础配置与安全频率 ---
st.set_page_config(page_title="2026 跨平台对冲终端", layout="wide")
st.title("🏹 跨平台“双引擎”实时监控对齐系统")

# 平台 API 终点
POLY_GAMMA = "https://gamma-api.polymarket.com"
POLY_CLOB = "https://clob.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心逻辑：获取实时深度与价格 ---
def get_live_depth(token_id, platform="poly"):
    """实时抓取订单簿并计算 1% 滑点深度"""
    try:
        url = f"{POLY_CLOB}/book?token_id={token_id}" if platform == "poly" else f"{PROB_API}/book?token_id={token_id}"
        r = requests.get(url, timeout=3).json()
        levels = r.get('asks', []) # 刷量买入看卖单
        if not levels: return 0.5, 0.0
        
        best_price = float(levels[0]['price'])
        limit = best_price * 1.01 # 锁定 1% 滑点
        total_depth = sum(float(l['price']) * float(l['size']) for l in levels if float(l['price']) <= limit)
        return best_price, round(total_depth, 2)
    except: return 0.5, 0.0

# --- 3. 核心对齐引擎：ID + 标题双重校验 ---
def sync_engine(kw, fuzz_threshold):
    now_utc = datetime.now(timezone.utc)
    
    # A. 抓取 Polymarket (全量活跃)
    poly_markets = []
    try:
        # 扫描前 200 个市场以覆盖 2026 最新热门
        for off in [0, 100]:
            r = requests.get(f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={off}").json()
            poly_markets.extend([m for m in r if float(m.get('liquidity', 0)) > 100])
    except: pass

    # B. 抓取 Probable (全量活跃)
    prob_markets = []
    try:
        r = requests.get(f"{PROB_API}/markets/?active=true&closed=false&limit=100").json()
        prob_markets = r.get('markets', [])
    except: pass

    # C. 混合对齐逻辑
    matches = []
    prob_id_map = {m['condition_id']: m for m in prob_markets if m.get('condition_id')}
    prob_titles = [m['question'] for m in prob_markets]

    for p in poly_markets:
        # 关键词过滤提速
        if kw and kw.lower() not in p['question'].lower(): continue
        
        target_prob = None
        # 方式 1: ID 精准匹配 (Hex ID)
        if p.get('conditionId') in prob_id_map:
            target_prob = prob_id_map[p['conditionId']]
        # 方式 2: 标题模糊匹配 (解决你手动能看到但 ID 没对上的问题)
        else:
            best = process.extractOne(p['question'], prob_titles, scorer=fuzz.token_set_ratio)
            if best and best[1] >= fuzz_threshold:
                target_prob = prob_markets[best[2]]

        if target_prob:
            # 提取代币 ID 进行价格与深度查询
            p_token = p['clobTokenIds'][0] if p.get('clobTokenIds') else ""
            b_token = target_prob['clobTokenIds'][0] if target_prob.get('clobTokenIds') else ""
            
            p_price, p_depth = get_live_depth(p_token, "poly")
            b_price, b_depth = get_live_depth(b_token, "prob")
            
            cost = p_price + (1 - b_price)
            matches.append({
                "市场名称": p['question'],
                "对冲成本": round(cost, 4),
                "深度 (Poly/Prob)": f"${p_depth:,.0f} / ${b_depth:,.0f}",
                "对齐方式": "ID 匹配" if p.get('conditionId') == target_prob.get('condition_id') else "标题对齐",
                "Poly 链接": f"https://polymarket.com/event/{p['slug']}",
                "Prob 链接": f"https://probable.markets/markets/{target_prob['market_slug']}?id={target_prob['id']}"
            })
    return pd.DataFrame(matches), len(poly_markets), len(prob_markets)

# --- 4. UI 渲染与侧边栏 ---
st.sidebar.header("⚙️ 2026 监控配置")
kw = st.sidebar.text_input("1️⃣ 搜索关键词 (如: BTC)", "BTC")
f_acc = st.sidebar.slider("2️⃣ 标题对齐精度", 40, 95, 75)
ref_sec = st.sidebar.slider("3️⃣ 刷新周期 (秒)", 60, 300, 180)

# 实时同步状态栏
status_placeholder = st.empty()
table_placeholder = st.empty()

while True:
    df, p_count, b_count = sync_engine(kw, f_acc)
    
    with status_placeholder.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Poly 活跃市场", p_count)
        c2.metric("Prob 活跃市场", b_count)
        c3.metric("成功对齐", len(df))
        st.write(f"✅ 最后同步: {datetime.now().strftime('%H:%M:%S')}")

    with table_placeholder.container():
        if not df.empty:
            st.dataframe(
                df.style.highlight_between(left=0.0, right=1.0, subset=['对冲成本'], color='#D4EDDA'),
                column_config={
                    "Poly 链接": st.column_config.LinkColumn("直达"),
                    "Prob 链接": st.column_config.LinkColumn("直达")
                }, use_container_width=True, hide_index=True
            )
        else:
            st.warning(f"当前搜索 '{kw}' 下未发现对齐市场。尝试调低‘标题对齐精度’。")
            
    time.sleep(ref_sec) # 遵循 Probable 3分钟缓存政策
    st.rerun()
