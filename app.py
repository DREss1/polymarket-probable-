import streamlit as st
import requests
import pandas as pd
import json

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
    col_m1.metric("🔵 Polymarket 活跃市场扫描", st.session_state['stats_poly_count'])
    col_m2.metric("🟠 Probable 活跃市场扫描", st.session_state['stats_prob_count'])
    col_m3.metric("🔗 成功匹配相同市场", st.session_state['stats_match_count'])

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
@st.cache_data(ttl=600)
def get_poly_markets():
    url = "https://gamma-api.polymarket.com/markets"
    params = {"active": "true", "closed": "false", "limit": 500}
    markets = []
    offset = 0
    try:
        while True:
            resp = requests.get(url, params={**params, "offset": offset}, timeout=20)
            if resp.status_code != 200: break 
            data = resp.json()
            if not data: break
            markets.extend(data)
            offset += 500
    except Exception as e:
        st.error(f"Polymarket 数据拉取失败: {e}")
    return markets

# --- 2. 获取 Probable 市场列表 ---
@st.cache_data(ttl=600)
def get_probable_markets():
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    try:
        while True:
            resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=20)
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
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                results.update(resp.json())
        except Exception as e:
            print(f"Probable 价格获取失败: {e}")
    return results

# --- 核心逻辑 ---
def load_and_process_data():
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        status_text.text("Step 1/3: 正在扫描 Polymarket 全量活跃市场...")
        poly = get_poly_markets()
        st.session_state['stats_poly_count'] = len(poly)
        progress_bar.progress(33)
        
        status_text.text("Step 2/3: 正在扫描 Probable 全量活跃市场...")
        prob = get_probable_markets()
        st.session_state['stats_prob_count'] = len(prob)
        progress_bar.progress(66)

        if not poly or not prob:
            st.error("无法获取数据，请检查网络后重试。")
            return

        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}
        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))
        
        st.session_state['stats_match_count'] = len(common_questions)

        if not common_questions:
            st.warning("没有找到名称完全相同的市场")
            st.session_state.master_df = pd.DataFrame()
            st.session_state.raw_arb_data = [] 
        else:
            status_text.text(f"Step 3/3: 正在同步 {len(common_questions)} 个市场的实时价格...")
            
            prob_token_map = {} 
            all_tokens_to_fetch = []
            for q in common_questions:
                prob_m = prob_dict[q]
                tokens = prob_m.get("tokens", [])
                prob_outcomes = parse_outcomes(prob_m.get("outcomes"))
                yes_token = next((t["token_id"] for t in tokens if t.get("outcome") == "Yes"), None)
                no_token = next((t["token_id"] for t in tokens if t.get("outcome") == "No"), None)
                prob_token_map[q] = {"Yes": yes_token, "No": no_token, "Outcomes": prob_outcomes}
                if yes_token: all_tokens_to_fetch.append(yes_token)
                if no_token: all_tokens_to_fetch.append(no_token)
            
            price_data = get_probable_prices_batch(all_tokens_to_fetch)
            progress_bar.progress(90)

            rows_data = [] 
            raw_arb_data = [] 

            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # --- Poly Data ---
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

                # --- Prob Data ---
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

                # --- 存储原始数据 (新增：记录价格和流动性，不立刻过滤) ---
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
                        "prob_liq": prob_liq
                    })

            columns = pd.MultiIndex.from_tuples([
                ("市场信息", "市场名称"),
                ("价格详情 (Outcome A / Outcome B)", "Polymarket"),
                ("价格详情 (Outcome A / Outcome B)", "Probable"),
                ("Polymarket 资金数据", "流动性 ($)"),
                ("Polymarket 资金数据", "24h 成交量 ($)"),
                ("Probable 资金数据", "流动性 ($)"),
                ("Probable 资金数据", "24h 成交量 ($)")
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
        st.button("❌ 重置筛选", on_click=clear_selection, use_container_width=True)

    if selected_market:
        filtered_df = df[df[market_col_key] == selected_market].copy()
    else:
        filtered_df = df.copy()

    format_cols = [
        ("Polymarket 资金数据", "流动性 ($)"),
        ("Polymarket 资金数据", "24h 成交量 ($)"),
        ("Probable 资金数据", "流动性 ($)"),
        ("Probable 资金数据", "24h 成交量 ($)")
    ]
    format_dict = {col: "${:,.0f}" for col in format_cols}
    
    styled_df = filtered_df.style.format(format_dict).set_properties(
        subset=format_cols, **{'text-align': 'center'}
    ).set_table_styles([{'selector': 'th', 'props': [('text-align', 'center'), ('vertical-align', 'middle')]}])

    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    st.caption(f"📊 当前显示 {len(filtered_df)} 条数据 (共 {len(df)} 条)")

    # ==========================================
    # 🚀 套利机会监测 (带流动性过滤)
    # ==========================================
    st.markdown("---") 
    
    with st.container(border=True):
        col_title, col_params = st.columns([1, 2])
        with col_title:
            st.subheader("🚀 套利机会扫描")
            st.caption("实时计算，自动过滤僵尸市场")
        
        with col_params:
            # 布局两个滑块：一个控利润，一个控流动性
            c1, c2 = st.columns(2)
            with c1:
                min_profit = st.slider(
                    "💰 最小利润率 (%)", 
                    0.0, 20.0, 1.0, 0.1,
                    help="过滤掉利润太小的机会"
                )
            with c2:
                # 新增：流动性过滤器
                min_liquidity = st.slider(
                    "💧 最小流动性过滤 ($)", 
                    0, 5000, 500, 100,
                    help="过滤掉流动性过低的市场（防止因无买卖盘导致的价格失真）"
                )
        
        arb_opportunities = []
        if 'raw_arb_data' in st.session_state and st.session_state.raw_arb_data:
            threshold_cost = 1.0 - (min_profit / 100.0)
            
            for item in st.session_state.raw_arb_data:
                name_a = item['outcome_a']
                name_b = item['outcome_b']
                poly_liq = item['poly_liq']
                prob_liq = item['prob_liq']

                # 🚫 核心修复：流动性检查
                # 如果任意一边的流动性低于设定值，直接跳过，视为无效/高风险市场
                if poly_liq < min_liquidity or prob_liq < min_liquidity:
                    continue

                # 🚫 核心修复：价格有效性检查
                # 如果价格极低 (< 0.01)，通常意味着没人在卖，是假价格，跳过
                MIN_VALID_PRICE = 0.01

                # 策略 A: Poly买A + Prob买B
                if item['poly_yes'] > MIN_VALID_PRICE and item['prob_no'] > MIN_VALID_PRICE:
                    cost_a = item['poly_yes'] + item['prob_no']
                    if cost_a < threshold_cost:
                        profit_pct = (1 - cost_a) / cost_a
                        max_cap = min(poly_liq, prob_liq)
                        arb_opportunities.append({
                            "市场": item['question'],
                            "策略": f"🔵Poly({name_a}) + 🟠Prob({name_b})",
                            "成本": cost_a,
                            "收益率": profit_pct,
                            "Poly池": poly_liq,
                            "Prob池": prob_liq,
                            "理论容量": max_cap
                        })
                
                # 策略 B: Poly买B + Prob买A
                if item['poly_no'] > MIN_VALID_PRICE and item['prob_yes'] > MIN_VALID_PRICE:
                    cost_b = item['poly_no'] + item['prob_yes']
                    if cost_b < threshold_cost:
                        profit_pct = (1 - cost_b) / cost_b
                        max_cap = min(poly_liq, prob_liq)
                        arb_opportunities.append({
                            "市场": item['question'],
                            "策略": f"🔵Poly({name_b}) + 🟠Prob({name_a})",
                            "成本": cost_b,
                            "收益率": profit_pct,
                            "Poly池": poly_liq,
                            "Prob池": prob_liq,
                            "理论容量": max_cap
                        })

        if arb_opportunities:
            arb_df = pd.DataFrame(arb_opportunities)
            arb_df = arb_df.sort_values(by="收益率", ascending=False)
            
            st.info(f"💡 在 '利润 > {min_profit}%' 且 '流动性 > ${min_liquidity}' 的条件下，筛选出 {len(arb_df)} 个有效套利机会！")
            
            styled_arb = arb_df.style.format({
                "成本": "${:.3f}",
                "收益率": "+{:.1%}",
                "Poly池": "${:,.0f}",
                "Prob池": "${:,.0f}",
                "理论容量": "${:,.0f}"
            })

            st.dataframe(
                styled_arb,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "策略": st.column_config.TextColumn("套利策略", width="large"),
                    "理论容量": st.column_config.NumberColumn("理论容量 (流动性瓶颈)", help="基于两边市场的最小流动性估算"),
                }
            )
        else:
            st.warning(f"🤷‍♂️ 未发现符合条件的套利机会。\n\n建议：\n1. 尝试调低 '最小利润率'\n2. 或调低 '最小流动性过滤' (注意风险)")

else:
    with col_search:
        st.info("👈 请点击右侧的 '刷新数据' 按钮开始全量抓取。")
