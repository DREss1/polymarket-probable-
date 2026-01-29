import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime, timezone

# --- 1. 基础配置与安全参数 ---
st.set_page_config(page_title="2026 职业对冲系统", layout="wide")
st.title("🛡️ 跨平台全量监控 & 滑点预警系统 (2026 稳定版)")

# 根据 image_e28360 设定的安全频率
POLY_DELAY = 1 / 15  # 每秒 15 次，安全规避 30次/s 的红线
# 根据 image_e27c99 设定的刷新周期
PROB_REFRESH = 180   # 3分钟同步一次

# --- 2. 核心补丁：404 链接修复与有效性校验 ---
def is_market_viable(m, now):
    """确保市场是 2026 年活跃且具备流动性的，彻底根除 404"""
    # 规则 A: 流动性必须充足 (僵尸市场 liquidity 必为 0)
    if float(m.get('liquidity', 0)) < 150: return False
    
    # 规则 B: 时间校验 (强制排除 2020-2024 的历史脏数据)
    end_str = m.get('endDate') or m.get('end_date')
    if end_str:
        try:
            end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            if end_date < now: return False # 已结算的不要
        except: pass
    
    # 规则 C: 排除明确标记为已关闭的市场
    if m.get('closed') is True or m.get('active') is False: return False
    return True

def fix_url(m, platform="poly"):
    """动态修正跳转链接，防止 ID 缺失导致的 404"""
    if platform == "poly":
        slug = m.get('slug', '')
        return f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/"
    else:
        # Probable 需要 slug 和 id 双重定位
        slug = m.get('market_slug') or m.get('slug', '')
        m_id = m.get('id', '')
        return f"https://probable.markets/markets/{slug}?id={m_id}"

# --- 3. 滑点深度预警 (基于 image_e37077) ---
def get_safe_volume(token_id, slippage_pct):
    """实时查询订单簿，计算指定滑点下的最大成交金额"""
    try:
        url = f"https://market-api.probable.markets/public/api/v1/book?token_id={token_id}"
        resp = requests.get(url, timeout=3).json()
        levels = resp.get('asks', []) # 刷量买入对应卖单
        if not levels: return 0.0
        
        limit_price = float(levels[0]['price']) * (1 + slippage_pct/100)
        total_usd = 0.0
        for l in levels:
            if float(l['price']) > limit_price: break
            total_usd += (float(l['price']) * float(l['size']))
        return round(total_usd, 2)
    except: return 0.0

# --- 4. 侧边栏：实时控制功能 ---
st.sidebar.header("⚙️ 扫描策略配置")
kw = st.sidebar.text_input("🔍 搜索关键词 (如: BTC)", "BTC")
f_acc = st.sidebar.slider("🎯 匹配精度 (越高越严)", 40, 95, 75)
slip_val = st.sidebar.slider("⚠️ 滑点容忍度 (%)", 0.1, 3.0, 1.0)

# --- 5. 主扫描逻辑 (带进度条) ---
def full_sync():
    now_utc = datetime.now(timezone.utc)
    poly_all = []
    prob_all = []
    
    # 初始化地毯式同步进度条
    prog = st.progress(0, text="正在启动 2026 全量活跃市场同步...")
    
    # A. 抓取 Polymarket (地毯式循环)
    for i in range(5): # 扫描前 500 个市场以覆盖 2026 热门区
        prog.progress(10 + i*10, text=f"正在同步 Polymarket 第 {i+1} 页...")
        url = f"https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            poly_all.extend([m for m in r if is_market_viable(m, now_utc)])
            time.sleep(POLY_DELAY)
        except: break

    # B. 抓取 Probable (基于总量翻页)
    try:
        prog.progress(70, text="正在同步 Probable 实时全量数据...")
        prob_url = "https://market-api.probable.markets/public/api/v1/markets/?active=true&closed=false&limit=100"
        r_prob = requests.get(prob_url, timeout=10).json()
        prob_all.extend([m for m in r_prob.get('markets', []) if is_market_viable(m, now_utc)])
    except: pass
    
    prog.progress(100, text="同步完成，正在计算对冲套利机会...")
    time.sleep(1)
    prog.empty()
    
    return poly_all, prob_all

# --- 6. 渲染循环 ---
placeholder = st.empty()
while True:
    p_raw, b_raw = full_sync()
    
    # 关键词预过滤 (提速 10 倍)
    if kw:
        p_raw = [m for m in p_raw if kw.lower() in m['question'].lower()]
        b_raw = [m for m in b_raw if kw.lower() in m['question'].lower()]

    matches = []
    b_titles = [m['question'] for m in b_raw]
    for p in p_raw:
        if not b_titles: break
        res = process.extractOne(p['question'], b_titles, scorer=fuzz.token_set_ratio)
        if res and res[1] >= f_acc:
            b = b_raw[res[2]]
            # 盈利公式：Cost = Poly_Yes + (1 - Prob_Yes)
            cost = float(p.get('best_yes_price', 0.5)) + (1 - float(b.get('yes_price', 0.5)))
            
            # 滑点限额计算
            safe_limit = 0.0
            if cost < 1.05 and len(b.get('clobTokenIds', [])) >= 2:
                safe_limit = get_safe_volume(b['clobTokenIds'][1], slip_val)
            
            matches.append({
                "活跃市场名称": p['question'],
                "对冲总成本": round(cost, 4),
                "套利收益": f"{(1-cost)*100:.2f}%" if cost < 1 else "-",
                f"{slip_val}%滑点限额": f"${safe_limit:,.0f}",
                "深度 (Poly/Prob)": f"${float(p['liquidity']):,.0f} / ${float(b['liquidity']):,.0f}",
                "去Poly交易": fix_url(p, "poly"),
                "去Prob交易": fix_url(b, "prob")
            })

    with placeholder.container():
        st.write(f"🔄 **数据全量更新于: {datetime.now().strftime('%H:%M:%S')}**")
        if matches:
            df = pd.DataFrame(matches).sort_values(by="对冲总成本")
            st.dataframe(
                df.style.highlight_between(left=0.9, right=1.0, subset=['对冲总成本'], color='#D4EDDA'),
                column_config={
                    "去Poly交易": st.column_config.LinkColumn("直达链接"),
                    "去Prob交易": st.column_config.LinkColumn("直达链接")
                }, use_container_width=True, hide_index=True
            )
            if any(df['对冲总成本'] < 1.0): 
                st.success("🔥 发现无损对冲机会！请根据安全限额下单。")
                st.balloons()
        else:
            st.warning(f"当前 '{kw}' 关键词下暂无 2026 年活跃对冲机会。")

    time.sleep(PROB_REFRESH)
    st.rerun()
