import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime

# --- 1. 安全配置中心 ---
st.set_page_config(page_title="2026 职业对冲系统-安全版", layout="wide")
st.title("🛡️ 职业级“零封禁”跨平台监控系统")

# 严格遵守 image_e28360 频率限制
POLY_MAX_RPS = 15  # 每秒请求数 (官方上限 30)
# 严格遵守 image_e27c99 缓存政策
PROB_SYNC_INTERVAL = 180 

# --- 2. 防封禁请求包装器 ---
def safe_request(url, method="GET", json_data=None):
    try:
        if method == "POST":
            resp = requests.post(url, json=json_data, timeout=10)
        else:
            resp = requests.get(url, timeout=10)
            
        if resp.status_code == 429: # 触发限速
            st.sidebar.error("⚠️ 触发平台限速！自动进入 60 秒冷静期...")
            time.sleep(60)
            return None
        return resp.json()
    except:
        return None

# --- 3. 穷尽式安全抓取 ---
def fetch_all_poly_safe():
    all_markets = []
    offset = 0
    while offset < 3000: # 假设全量约为 3000 个
        url = f"https://gamma-api.polymarket.com/markets?active=true&limit=100&offset={offset}"
        data = safe_request(url)
        if not data: break
        all_markets.extend(data)
        offset += 100
        time.sleep(1 / POLY_MAX_RPS) # 主动限速
    return all_markets

def fetch_all_prob_safe():
    all_markets = []
    base_url = "https://market-api.probable.markets/public/api/v1/markets/"
    first = safe_request(f"{base_url}?active=true&limit=100&page=1")
    if not first: return []
    
    all_markets.extend(first.get('markets', []))
    total_results = first.get('pagination', {}).get('totalResults', 0)
    total_pages = (total_results // 100) + 1
    
    # 对 Probable 使用较低并发，保护节点
    for p in range(2, total_pages + 1):
        data = safe_request(f"{base_url}?active=true&limit=100&page={p}")
        if data: all_markets.extend(data.get('markets', []))
        time.sleep(0.5) # 基础间隔
    return all_markets

# --- 4. 深度与匹配逻辑 ---
def get_slippage_limit(token_id, slippage_pct):
    """基于 image_e37077 订单簿计算限额"""
    url = f"https://market-api.probable.markets/public/api/v1/book?token_id={token_id}"
    res = safe_request(url)
    if not res: return 0.0
    # 刷量通常是买单吃 asks
    levels = res.get('asks', [])
    if not levels: return 0.0
    base = float(levels[0]['price'])
    limit = base * (1 + slippage_pct/100)
    safe_vol = 0.0
    for l in levels:
        if float(l['price']) > limit: break
        safe_vol += (float(l['price']) * float(l['size']))
    return safe_vol

# --- 5. 主监控循环 ---
st.sidebar.header("📊 监控中心控制台")
keyword = st.sidebar.text_input("过滤关键词", "BTC")
fuzz_score = st.sidebar.slider("标题对齐精度", 40, 95, 70)
slip_target = st.sidebar.slider("允许滑点 (%)", 0.1, 2.0, 1.0)

placeholder = st.empty()
while True:
    st.sidebar.info("🔄 正在启动全量同步...")
    poly = fetch_all_poly_safe()
    prob = fetch_all_prob_safe()
    
    matches = []
    if poly and prob:
        prob_titles = [m['question'] for m in prob]
        for p in poly:
            # 关键词过滤，极大提高匹配速度
            if keyword.lower() not in p['question'].lower(): continue
            
            res = process.extractOne(p['question'], prob_titles, scorer=fuzz.token_set_ratio)
            if res and res[1] >= fuzz_score:
                b = prob[res[2]]
                cost = float(p.get('best_yes_price', 0.5)) + (1 - float(b.get('yes_price', 0.5)))
                
                # 只有盈利潜力大的才去查订单簿，节省 API 额度
                safe_depth = 0.0
                if cost < 1.03:
                    safe_depth = get_slippage_limit(b['clobTokenIds'][1], slip_target)
                
                matches.append({
                    "对冲市场": p['question'],
                    "对冲总成本": round(cost, 4),
                    "滑点内安全深度 ($)": round(safe_depth, 2),
                    "盈利预期": f"{(1-cost)*100:.2f}%" if cost < 1 else "-",
                    "去Poly交易": f"https://polymarket.com/event/{p['slug']}",
                    "去Prob交易": f"https://probable.markets/markets/{b['market_slug']}"
                })

    with placeholder.container():
        st.write(f"✅ 全量扫描完成 - 扫描时间: {datetime.now().strftime('%H:%M:%S')}")
        if matches:
            df = pd.DataFrame(matches).sort_values(by="对冲总成本")
            st.dataframe(df.style.highlight_between(left=0.9, right=1.0, subset=['对冲总成本'], color='#D4EDDA'), 
                         column_config={
                             "去Poly交易": st.column_config.LinkColumn("直达"),
                             "去Prob交易": st.column_config.LinkColumn("直达")
                         }, use_container_width=True)
        else: st.warning("未发现匹配。建议调低匹配精度。")

    st.sidebar.warning(f"⏸️ 进入平台建议的 {PROB_SYNC_INTERVAL}秒 缓存等待期...")
    time.sleep(PROB_SYNC_INTERVAL)
    st.rerun()
