import streamlit as st
import pandas as pd
import requests
import time
from rapidfuzz import fuzz, process
from datetime import datetime, timezone

# --- 1. 基础配置 ---
st.set_page_config(page_title="2026 极速纯净监控", layout="wide")
st.title("🏹 跨平台“全量活跃”对冲系统")

# 侧边栏控制
st.sidebar.header("🎯 扫描控制")
kw = st.sidebar.text_input("1. 关键词过滤 (如 BTC)", "BTC")
f_val = st.sidebar.slider("2. 匹配精度", 40, 95, 75)
min_liq = st.sidebar.number_input("3. 最低流动性 ($)", value=200)

# --- 2. 核心校验函数：排除僵尸市场 ---
def is_truly_live(m):
    """确保市场是 2026 年活跃且有深度的"""
    now = datetime.now(timezone.utc)
    
    # 过滤 1: API 状态必须为未关闭
    if m.get('closed') is True or m.get('active') is False:
        return False
        
    # 过滤 2: 时间必须在未来
    end_str = m.get('endDate') or m.get('end_date')
    if end_str:
        try:
            end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            if end_date < now: return False
        except: pass
        
    # 过滤 3: 必须有真金白银的深度 (排除 404 幽灵)
    if float(m.get('liquidity', 0)) < min_liq:
        return False
        
    return True

# --- 3. 全量数据抓取逻辑 ---
def fetch_all():
    progress = st.progress(0, text="正在地毯式搜寻 2026 年活跃市场...")
    
    # Polymarket 全量扫描 (带翻页)
    poly_res = []
    for off in range(0, 500, 100):
        progress.progress(10 + off//10, text=f"同步 Polymarket 第 {off//100 + 1} 页...")
        r = requests.get(f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={off}").json()
        poly_res.extend([m for m in r if is_truly_live(m)])
        time.sleep(0.1)

    # Probable 全量扫描
    progress.progress(70, text="正在同步 Probable 实时数据...")
    prob_res = []
    try:
        r_prob = requests.get("https://market-api.probable.markets/public/api/v1/markets/?active=true&closed=false&limit=100").json()
        prob_res = [m for m in r_prob.get('markets', []) if is_truly_live(m)]
    except: pass
    
    progress.empty()
    return poly_res, prob_res

# --- 4. 渲染循环 ---
placeholder = st.empty()
while True:
    poly, prob = fetch_all()
    
    matches = []
    if poly and prob:
        # 关键词预过滤，提速 10 倍
        if kw:
            poly = [m for m in poly if kw.lower() in m['question'].lower()]
            prob = [m for m in prob if kw.lower() in m['question'].lower()]

        prob_titles = [m['question'] for m in prob]
        for p in poly:
            if not prob_titles: break
            res = process.extractOne(p['question'], prob_titles, scorer=fuzz.token_set_ratio)
            if res and res[1] >= f_val:
                b = prob[res[2]]
                cost = float(p.get('best_yes_price', 0.5)) + (1 - float(b.get('yes_price', 0.5)))
                
                matches.append({
                    "市场名称": p['question'],
                    "对冲成本": round(cost, 4),
                    "收益": f"{(1-cost)*100:.2f}%",
                    "深度 (Poly/Prob)": f"${float(p['liquidity']):,.0f} / ${float(b['liquidity']):,.0f}",
                    "去 Poly": f"https://polymarket.com/event/{p['slug']}",
                    "去 Prob": f"https://probable.markets/markets/{b['market_slug']}"
                })

    with placeholder.container():
        st.write(f"⏰ 数据更新: {datetime.now().strftime('%H:%M:%S')}")
        if matches:
            df = pd.DataFrame(matches).sort_values(by="对冲成本")
            st.dataframe(df, column_config={
                "去 Poly": st.column_config.LinkColumn("直达"),
                "去 Prob": st.column_config.LinkColumn("直达")
            }, use_container_width=True, hide_index=True)
            if any(df['对冲成本'] < 1.0): st.success("💰 发现盈利机会！"); st.balloons()
        else:
            st.info(f"在 2026 活跃市场中未发现关于 '{kw}' 的匹配，请尝试调低精度。")

    time.sleep(180) # 配合 Probable 3分钟缓存政策
    st.rerun()
