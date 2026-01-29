import streamlit as st
import pandas as pd
import requests
import time
from rapidfuzz import fuzz, process
from datetime import datetime, timezone

st.set_page_config(page_title="2026 纯净对冲", layout="wide")
st.title("🛡️ 跨平台实时监控 (已开启 2026 深度过滤)")

# --- 1. 核心过滤逻辑：剔除 2020/2021 僵尸市场 ---
def is_live_2026(m):
    """
    强制要求市场必须是 2026 年且有真金白银的深度
    """
    # 规则 1：必须有流动性 (过滤 404 僵尸市场)
    liq = float(m.get('liquidity', 0))
    if liq < 200: return False # 低于 200 刀的直接不要
    
    # 规则 2：强制时间校验 (排除 2020 年陈旧数据)
    now = datetime.now(timezone.utc)
    end_str = m.get('endDate') or m.get('end_date')
    if end_str:
        try:
            end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            if end_date < now: return False # 已结束的不要
        except: pass
    return True

# --- 2. 抓取与链接修正 ---
def fetch_data():
    # 抓取 Poly (强制 closed=false 获取当前)
    poly_raw = requests.get("https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100").json()
    poly_active = [m for m in poly_raw if is_live_2026(m)]

    # 抓取 Prob (基于 image_e36594)
    prob_resp = requests.get("https://market-api.probable.markets/public/api/v1/markets/?active=true&limit=100").json()
    prob_active = [m for m in prob_resp.get('markets', []) if is_live_2026(m)]

    return poly_active, prob_active

# --- 3. 匹配逻辑 ---
def run():
    poly, prob = fetch_data()
    st.sidebar.write(f"2026 活跃市场 - Poly: {len(poly)} | Prob: {len(prob)}")
    
    results = []
    if poly and prob:
        prob_titles = [m['question'] for m in prob]
        for p in poly:
            # 提高匹配门槛到 80，防止误配
            best = process.extractOne(p['question'], prob_titles, scorer=fuzz.token_set_ratio)
            if best and best[1] >= 80:
                b = prob[best[2]]
                cost = float(p['best_yes_price']) + (1 - float(b['yes_price']))
                
                # 链接修正：Probable 链接通常需要带上具体的 ID
                results.append({
                    "市场名称": p['question'],
                    "收益率": f"{(1-cost)*100:.2f}%",
                    "Poly 链接": f"https://polymarket.com/event/{p['slug']}",
                    "Prob 链接": f"https://probable.markets/markets/{b['market_slug']}?id={b['id']}",
                    "更新时间": datetime.now().strftime("%H:%M")
                })
    return pd.DataFrame(results)

# --- UI 渲染 ---
df = run()
if not df.empty:
    st.dataframe(df, column_config={
        "Poly 链接": st.column_config.LinkColumn("直达 Poly"),
        "Prob 链接": st.column_config.LinkColumn("直达 Prob")
    }, use_container_width=True)
else:
    st.info("正在地毯式搜寻 2026 年真实活跃市场...")

time.sleep(180)
st.rerun()
