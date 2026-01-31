import streamlit as st
import requests
import pandas as pd
import json
import time

st.set_page_config(page_title="Polymarket vs Probable 市场对比", page_icon="📊", layout="wide")

st.title("Polymarket vs Probable 相同市场名称对比工具")
st.markdown("显示名称完全相同的市场，并附带双边价格、流动性与成交量对比")

# --- 0. 初始化 Session State ---
if 'stats_poly_count' not in st.session_state: st.session_state['stats_poly_count'] = 0
if 'stats_prob_count' not in st.session_state: st.session_state['stats_prob_count'] = 0
if 'stats_match_count' not in st.session_state: st.session_state['stats_match_count'] = 0

# ==========================================
# 📊 顶部常驻仪表盘
# ==========================================
with st.container(border=True):
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("🔵 Polymarket 活跃市场", st.session_state['stats_poly_count'])
    col_m2.metric("🟠 Probable 活跃市场", st.session_state['stats_prob_count'])
    col_m3.metric("🔗 匹配成功", st.session_state['stats_match_count'])

# --- 辅助函数 ---
def safe_float(val):
    try:
        if val is None or val == "": return 0.0
        return float(val)
    except: return 0.0

def clear_selection():
    st.session_state["market_select"] = None

def parse_outcomes(outcomes_str):
    default = ["Yes", "No"]
    if not outcomes_str: return default
    try:
        if isinstance(outcomes_str, str):
            data = json.loads(outcomes_str)
            if isinstance(data, list) and len(data) >= 2: return data
        elif isinstance(outcomes_str, list) and len(outcomes_str) >= 2:
            return outcomes_str
    except: pass
    return default

# --- 1. 获取 Polymarket 数据 ---
@st.cache_data(ttl=60)
def get_poly_markets():
    url = "https://gamma-api.polymarket.com/markets"
    params = {"active": "true", "closed": "false", "limit": 500}
    markets = []
    offset = 0
    try:
        while True:
            resp = requests.get(url, params={**params, "offset": offset}, timeout=10)
            if resp.status_code != 200: break 
            data = resp.json()
            if not data: break
            markets.extend(data)
            offset += 500
    except Exception as e:
        st.error(f"Polymarket 数据拉取失败: {e}")
    return markets

# --- 2. 获取 Probable 市场列表 ---
@st.cache_data(ttl=60)
def get_probable_markets():
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    try:
        while True:
            resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=10)
            if resp.status_code != 200: break
            data = resp.json()
            new = data.get("markets", []) 
            if not new: break
            markets.extend(new)
            page += 1
    except Exception as e:
        st.error(f"Probable 列表拉取失败: {e}")
    return markets

# --- 3. 批量获取 Probable 价格 ---
def get_probable_prices_batch(token_ids):
    if not token_ids: return {}
    url = "https://api.probable.markets/public/api/v1/prices"
    results = {}
    chunk_size = 50
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i+chunk_size]
        payload = [{"token_id": t, "side": "BUY"} for t in chunk]
        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                results.update(resp.json())
        except Exception as e:
            pass
    return results

# --- 4. 真实深度计算函数 ---
def calculate_arb_capacity(poly_id, prob_id):
    """
    计算两边都能成交的最小深度。
    为了更宽容地捕捉机会，这里统计 Ask Price * 1.2 (20%滑点) 范围内的所有挂单。
    """
    capacity_poly = 0.0
    capacity_prob = 0.0
    
    # 1. 获取 Polymarket 深度
    try:
        url = f"https://clob.polymarket.com/book?token_id={poly_id}"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            asks = resp.json().get("asks", [])
            if asks:
                # 统计当前 BestAsk 往上 20% 价格区间内的所有深度
                best_p = float(asks[0]["price"])
                limit_p = best_p * 1.20 
                for item in asks:
                    p = float(item["price"])
                    s = float(item["size"])
                    if p > limit_p: break
                    capacity_poly += p * s
    except: pass

    # 2. 获取 Probable 深度
    try:
        url = f"https://api.probable.markets/public/api/v1/book?token_id={prob_id}"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            asks = resp.json().get("asks", [])
            if asks:
                best_p = float(asks[0][0])
                limit_p = best_p * 1.20
                for item in asks:
                    p = float(item[0])
                    s = float(item[1])
                    if p > limit_p: break
                    capacity_prob += p * s
    except: pass
    
    return min(capacity_poly, capacity_prob)

# --- 核心逻辑 ---
def load_and_process_data():
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        status_text.text("Step 1/4: 扫描 Polymarket...")
        poly = get_poly_markets()
        st.session_state['stats_poly_count'] = len(poly)
        progress_bar.progress(25)
        
        status_text.text("Step 2/4: 扫描 Probable...")
        prob = get_probable_markets()
        st.session_state['stats_prob_count'] = len(prob)
        progress_bar.progress(50)

        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}
        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))
        
        st.session_state['stats_match_count'] = len(common_questions)

        if not common_questions:
            st.warning("无相同市场")
            st.session_state.master_df = pd.DataFrame()
            st.session_state.raw_arb_data = [] 
        else:
            status_text.text(f"Step 3/4: 同步 {len(common_questions)} 个市场的价格...")
            
            prob_token_map = {} 
            all_tokens_to_fetch = []
            poly_token_map = {} 

            for q in common_questions:
                prob_m = prob_dict[q]
                p_tokens = prob_m.get("tokens", [])
                p_outcomes = parse_outcomes(prob_m.get("outcomes"))
                p_yes = next((t["token_id"] for t in p_tokens if t.get("outcome") == "Yes"), None)
                p_no = next((t["token_id"] for t in p_tokens if t.get("outcome") == "No"), None)
                prob_token_map[q] = {"Yes": p_yes, "No": p_no, "Outcomes": p_outcomes}
                if p_yes: all_tokens_to_fetch.append(p_yes)
                if p_no: all_tokens_to_fetch.append(p_no)

                poly_m = poly_dict[q]
                poly_yes_id = None
                poly_no_id = None
                if "clobTokenIds" in poly_m:
                    ids = json.loads(poly_m["clobTokenIds"]) if isinstance(poly_m["clobTokenIds"], str) else poly_m["clobTokenIds"]
                    if len(ids) >= 2:
                        poly_yes_id = ids[0]
                        poly_no_id = ids[1]
                poly_token_map[q] = {"Yes": poly_yes_id, "No": poly_no_id}
            
            price_data = get_probable_prices_batch(all_tokens_to_fetch)
            progress_bar.progress(75)

            rows_data = [] 
            raw_arb_data = [] 

            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]
                outcomes_list = parse_outcomes(poly_m.get("outcomes"))
                name_a = outcomes_list[0]
                name_b = outcomes_list[1] if len(outcomes_list) > 1 else "No"
                
                raw_prices = poly_m.get("outcomePrices", [])
                if isinstance(raw_prices, str):
                    try: prices = json.loads(raw_prices)
                    except: prices = []
                else: prices = raw_prices
                
                try:
                    poly_p_yes = float(prices[0]) if len(prices) > 0 else 0.0
                    poly_p_no = float(prices[1]) if len(prices) > 1 else 0.0
                    poly_price_str = f"{name_a}: {poly_p_yes:.1%} / {name_b}: {poly_p_no:.1%}"
                except: 
                    poly_p_yes, poly_p_no = 0.0, 0.0
                    poly_price_str = "Err"
                
                poly_liq = safe_float(poly_m.get("liquidity", 0))
                poly_vol = safe_float(poly_m.get("volume24hr", 0))
                if poly_vol == 0: poly_vol = safe_float(poly_m.get("volume", 0))

                prob_info = prob_token_map.get(q, {})
                id_yes = prob_info.get("Yes")
                id_no = prob_info.get("No")
                prob_raw_yes = price_data.get(id_yes, {}).get("BUY", "0") if id_yes else "0"
                prob_raw_no = price_data.get(id_no, {}).get("BUY", "0") if id_no else "0"
                try:
                    prob_p_yes = float(prob_raw_yes)
                    prob_p_no = float(prob_raw_no)
                    prob_price_str = f"{name_a}: {prob_p_yes:.1%} / {name_b}: {prob_p_no:.1%}"
                except: 
                    prob_p_yes, prob_p_no = 0.0, 0.0
                    prob_price_str = "N/A"
                prob_liq = safe_float(prob_m.get("liquidity", 0))
                prob_vol = safe_float(prob_m.get("volume24hr", 0))

                rows_data.append([
                    poly_m["question"],
                    poly_price_str, prob_price_str,
                    poly_liq, poly_vol,
                    prob_liq, prob_vol
                ])

                # 存储数据
                if poly_p_yes > 0 or poly_p_no > 0: 
                    raw_arb_data.append({
                        "question": poly_m["question"],
                        "outcome_a": name_a,
                        "outcome_b": name_b,
                        "poly_yes": poly_p_yes,
                        "poly_no": poly_p_no,
                        "prob_yes": prob_p_yes,
                        "prob_no": prob_p_no,
                        "poly_liq": poly_liq,
                        "prob_liq": prob_liq,
                        "prob_yes_id": id_yes,
                        "prob_no_id": id_no,
                        "poly_yes_id": poly_token_map[q]["Yes"],
                        "poly_no_id": poly_token_map[q]["No"]
                    })

            columns = pd.MultiIndex.from_tuples([
                ("市场信息", "市场名称"),
                ("价格详情", "Polymarket"), 
                ("价格详情", "Probable"),   
                ("Polymarket 资金", "流动性 ($)"),
                ("Polymarket 资金", "24h 量 ($)"),
                ("Probable 资金", "流动性 ($)"),
                ("Probable 资金", "24h 量 ($)")
            ])
            st.session_state.master_df = pd.DataFrame(rows_data, columns=columns)
            st.session_state.raw_arb_data = raw_arb_data
            
            status_text.success(f"数据加载完成！")
            progress_bar.empty()
            st.rerun()

    except Exception as e:
        st.error(f"发生错误: {e}")

# --- 主界面 UI ---

col_search, col_reset, col_refresh = st.columns([5, 1, 1], gap="small")

with col_refresh:
    st.write("") 
    st.write("") 
    if st.button("🔄 刷新数据", type="primary", use_container_width=True):
        load_and_process_data()

if 'master_df' in st.session_state and not st.session_state.master_df.empty:
    df = st.session_state.master_df
    
    market_col_key = ("市场信息", "市场名称")
    with col_search:
        market_options = df[market_col_key].tolist()
        selected_market = st.selectbox(
            "🔍 搜索/筛选市场", 
            options=market_options,
            index=None,
            key="market_select",
            placeholder="输入关键词...",
        )

    with col_reset:
        st.write("")
        st.write("")
        st.button("❌ 重置", on_click=clear_selection, use_container_width=True)

    if selected_market:
        filtered_df = df[df[market_col_key] == selected_market].copy()
    else:
        filtered_df = df.copy()

    format_cols = [
        ("Polymarket 资金", "流动性 ($)"),
        ("Polymarket 资金", "24h 量 ($)"),
        ("Probable 资金", "流动性 ($)"),
        ("Probable 资金", "24h 量 ($)")
    ]
    format_dict = {col: "${:,.0f}" for col in format_cols}
    
    styled_df = filtered_df.style.format(format_dict).set_properties(
        subset=format_cols, **{'text-align': 'center'}
    ).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center'), ('vertical-align', 'middle')]}])

    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    st.caption(f"📊 当前显示 {len(filtered_df)} 条数据")

    # ==========================================
    # 🚀 套利机会监测 (完美修复版)
    # ==========================================
    st.markdown("---") 
    
    with st.container(border=True):
        st.subheader("🚀 套利机会扫描 (Arbitrage)")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            min_profit = st.slider("💰 最小利润率 (%) - 设置为 0 可查看所有机会", 0.0, 50.0, 0.0, 0.1)
        with c2:
            st.write("")
            st.write("")
            # 修改 1: 默认设置为 False (关闭自动计算)
            auto_depth = st.toggle("⚡ 自动计算真实套利容量 (Auto-Calc Depth)", value=False)

        if 'raw_arb_data' in st.session_state and st.session_state.raw_arb_data:
            threshold_cost = 1.0 - (min_profit / 100.0)
            
            candidates = []
            
            # 1. 快速筛选
            for item in st.session_state.raw_arb_data:
                if item['poly_yes'] <= 0 or item['prob_no'] <= 0 or item['poly_no'] <= 0 or item['prob_yes'] <= 0:
                    continue

                name_buy = ""
                name_sell = ""
                strat_name = ""

                # A: Poly Yes + Prob No
                cost_a = item['poly_yes'] + item['prob_no']
                if cost_a < threshold_cost:
                    name_buy = item['outcome_a']
                    name_sell = item['outcome_b']
                    strat_name = f"🔵Poly({name_buy}) + 🟠Prob({name_sell})"
                    candidates.append({**item, "strat": "A", "cost": cost_a, "raw_profit": (1-cost_a)/cost_a, "strategy_name": strat_name})
                
                # B: Poly No + Prob Yes
                cost_b = item['poly_no'] + item['prob_yes']
                if cost_b < threshold_cost:
                    name_buy = item['outcome_b']
                    name_sell = item['outcome_a']
                    strat_name = f"🔵Poly({name_buy}) + 🟠Prob({name_sell})"
                    candidates.append({**item, "strat": "B", "cost": cost_b, "raw_profit": (1-cost_b)/cost_b, "strategy_name": strat_name})

            # 准备数据框架
            final_data = []

            # 2. 逻辑分支：开/关
            if not auto_depth:
                # 关闭状态：只显示基本信息，容量列显示 "未计算"
                st.info("ℹ️ 深度计算已关闭。显示的收益率仅基于最新成交价/最优价，可能包含无流动性的虚假机会。")
                for cand in candidates:
                    final_data.append({
                        "市场": cand['question'],
                        "策略": cand['strategy_name'],
                        "成本": cand['cost'],
                        "收益率": cand['raw_profit'],
                        "真实可套利金额": None # 标记为 None
                    })
            else:
                # 开启状态：计算深度，并过滤掉垃圾机会
                status_box = st.empty()
                sorted_candidates = sorted(candidates, key=lambda x: x['raw_profit'], reverse=True)[:50]
                
                for idx, cand in enumerate(sorted_candidates):
                    status_box.text(f"正在验算深度 ({idx+1}/{len(sorted_candidates)}): {cand['question']}...")
                    
                    poly_side_id = cand['poly_yes_id'] if cand['strat'] == 'A' else cand['poly_no_id']
                    prob_side_id = cand['prob_no_id'] if cand['strat'] == 'A' else cand['prob_yes_id']
                    
                    real_capacity = calculate_arb_capacity(poly_side_id, prob_side_id)
                    
                    # 修改 3: 核心过滤！如果真实容量 < $1，直接丢弃，不显示！
                    if real_capacity > 1.0: 
                        final_data.append({
                            "市场": cand['question'],
                            "策略": cand['strategy_name'],
                            "成本": cand['cost'],
                            "收益率": cand['raw_profit'],
                            "真实可套利金额": real_capacity
                        })
                status_box.empty()

            # 3. 统一渲染表格
            if final_data:
                final_df = pd.DataFrame(final_data)
                final_df = final_df.sort_values(by="收益率", ascending=False)
                
                if auto_depth:
                    st.success(f"✅ 验算完成！发现 {len(final_df)} 个真实有效的套利机会 (已剔除容量 < $1 的虚假市场)。")
                else:
                    st.warning(f"⚠️ 发现 {len(final_df)} 个理论机会。请打开上方开关以验证真实性。")

                # 样式处理
                styled_final = final_df.style.format({
                    "成本": "${:.3f}",
                    "收益率": "+{:.1%}",
                    "真实可套利金额": "${:,.2f}",
                }, na_rep="未计算") # None 显示为 "未计算"

                st.dataframe(
                    styled_final,
                    use_container_width=True
