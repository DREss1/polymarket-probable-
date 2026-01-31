import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="Polymarket vs Probable 市场对比", page_icon="📊", layout="wide")

st.title("Polymarket vs Probable 相同市场名称对比工具")
st.markdown("显示名称完全相同的市场，并附带双边价格、流动性与成交量对比")

# --- 辅助函数：安全转换浮点数 ---
def safe_float(val):
    try:
        if val is None or val == "":
            return 0.0
        return float(val)
    except:
        return 0.0

# --- 回调函数：一键清空 ---
def clear_selection():
    st.session_state["market_select"] = None

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
            if offset > 5000: break 
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
            if page > 50: break
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

# --- 核心逻辑：加载数据 (只负责抓取和存原始数据) ---
def load_and_process_data():
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        # Step 1
        status_text.text("Step 1/3: 正在获取 Polymarket 数据...")
        poly = get_poly_markets()
        progress_bar.progress(33)
        
        # Step 2
        status_text.text("Step 2/3: 正在获取 Probable 数据...")
        prob = get_probable_markets()
        progress_bar.progress(66)

        if not poly or not prob:
            st.error("无法获取数据，请检查网络后重试。")
            return

        # 匹配逻辑
        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}
        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))

        if not common_questions:
            st.warning("没有找到名称完全相同的市场")
            st.session_state.master_df = pd.DataFrame()
            st.session_state.raw_arb_data = [] # 清空原始数据
        else:
            status_text.text(f"Step 3/3: 正在同步 {len(common_questions)} 个市场的实时价格...")
            
            # 提取 Token ID
            prob_token_map = {} 
            all_tokens_to_fetch = []
            for q in common_questions:
                prob_m = prob_dict[q]
                tokens = prob_m.get("tokens", [])
                yes_token = next((t["token_id"] for t in tokens if t.get("outcome") == "Yes"), None)
                no_token = next((t["token_id"] for t in tokens if t.get("outcome") == "No"), None)
                prob_token_map[q] = {"Yes": yes_token, "No": no_token}
                if yes_token: all_tokens_to_fetch.append(yes_token)
                if no_token: all_tokens_to_fetch.append(no_token)
            
            # 批量获取价格
            price_data = get_probable_prices_batch(all_tokens_to_fetch)
            progress_bar.progress(90)

            rows_data = [] 
            raw_arb_data = [] # 新增：用于存储原始浮点数数据，方便后续动态计算

            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # --- Polymarket ---
                raw_prices = poly_m.get("outcomePrices", [])
                if isinstance(raw_prices, str):
                    try: prices = json.loads(raw_prices)
                    except: prices = []
                else: prices = raw_prices
                
                try:
                    poly_p_yes = float(prices[0]) if len(prices) > 0 else 0.0
                    poly_p_no = float(prices[1]) if len(prices) > 1 else 0.0
                    poly_price_str = f"{poly_p_yes:.1%} / {poly_p_no:.1%}"
                except: 
                    poly_p_yes, poly_p_no = 0.0, 0.0
                    poly_price_str = "Err"
                
                poly_liq = safe_float(poly_m.get("liquidity", 0))
                poly_vol = safe_float(poly_m.get("volume24hr", 0))
                if poly_vol == 0: poly_vol = safe_float(poly_m.get("volume", 0))

                # --- Probable ---
                prob_ids = prob_token_map.get(q, {})
                id_yes = prob_ids.get("Yes")
                id_no = prob_ids.get("No")
                prob_raw_yes = price_data.get(id_yes, {}).get("BUY", "0") if id_yes else "0"
                prob_raw_no = price_data.get(id_no, {}).get("BUY", "0") if id_no else "0"
                
                try:
                    prob_p_yes = float(prob_raw_yes)
                    prob_p_no = float(prob_raw_no)
                    prob_price_str = f"{prob_p_yes:.1%} / {prob_p_no:.1%}"
                except: 
                    prob_p_yes, prob_p_no = 0.0, 0.0
                    prob_price_str = "N/A"
                
                prob_liq = safe_float(prob_m.get("liquidity", 0))
                prob_vol = safe_float(prob_m.get("volume24hr", 0))

                # --- 1. 填充主展示表 ---
                rows_data.append([
                    poly_m["question"],
                    poly_price_str, prob_price_str,
                    poly_liq, poly_vol,
                    prob_liq, prob_vol
                ])

                # --- 2. 存储原始数据 (用于动态套利计算) ---
                if poly_p_yes > 0 or poly_p_no > 0: # 只存有效数据
                    raw_arb_data.append({
                        "question": poly_m["question"],
                        "poly_yes": poly_p_yes,
                        "poly_no": poly_p_no,
                        "prob_yes": prob_p_yes,
                        "prob_no": prob_p_no,
                        "poly_liq": poly_liq,
                        "prob_liq": prob_liq
                    })

            # 保存主展示表
            columns = pd.MultiIndex.from_tuples([
                ("市场信息", "市场名称"),
                ("价格 (Yes/No)", "Polymarket"),
                ("价格 (Yes/No)", "Probable"),
                ("Polymarket 资金数据", "流动性 ($)"),
                ("Polymarket 资金数据", "24h 成交量 ($)"),
                ("Probable 资金数据", "流动性 ($)"),
                ("Probable 资金数据", "24h 成交量 ($)")
            ])
            st.session_state.master_df = pd.DataFrame(rows_data, columns=columns)
            
            # 保存原始数据到 Session State
            st.session_state.raw_arb_data = raw_arb_data
            
            status_text.success(f"数据加载完成！共找到 {len(common_questions)} 个相同市场。")
            progress_bar.empty()
            
    except Exception as e:
        st.error(f"发生错误: {e}")

# --- 主界面 UI ---

col_search, col_reset, col_refresh = st.columns([5, 1, 1], gap="small")

with col_refresh:
    st.write("") 
    st.write("") 
    if st.button("🔄 刷新数据", type="primary", use_container_width=True):
        load_and_process_data()

# 检查是否有数据
if 'master_df' in st.session_state and not st.session_state.master_df.empty:
    df = st.session_state.master_df
    
    # --- 1. 搜索区 ---
    market_col_key = ("市场信息", "市场名称")
    with col_search:
        market_options = df[market_col_key].tolist()
        selected_market = st.selectbox(
            "🔍 搜索/筛选市场 (输入关键词自动联想)", 
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

    # --- 2. 主数据表展示 ---
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
    # 🚀 套利机会监测 (动态阈值版)
    # ==========================================
    st.markdown("---") 
    
    with st.container(border=True):
        col_title, col_slider = st.columns([2, 1])
        with col_title:
            st.subheader("🚀 套利机会扫描 (Arbitrage Opportunities)")
        
        # --- 新增功能：阈值设置滑块 ---
        with col_slider:
            min_profit = st.slider(
                "设置最小套利利润率 (%)", 
                min_value=0.0, 
                max_value=20.0, 
                value=1.0, 
                step=0.1,
                help="过滤掉利润低于此值的机会。例如 1.0% 意味着两边总成本需低于 $0.99"
            )
        
        # 动态计算逻辑
        arb_opportunities = []
        if 'raw_arb_data' in st.session_state and st.session_state.raw_arb_data:
            threshold_cost = 1.0 - (min_profit / 100.0)
            
            for item in st.session_state.raw_arb_data:
                # 策略 A
                if item['poly_yes'] > 0 and item['prob_no'] > 0:
                    cost_a = item['poly_yes'] + item['prob_no']
                    if cost_a < threshold_cost:
                        profit_pct = (1 - cost_a) / cost_a
                        max_cap = min(item['poly_liq'], item['prob_liq'])
                        arb_opportunities.append({
                            "市场": item['question'],
                            "策略": "🔵Poly(Yes) + 🟠Prob(No)",
                            "成本": cost_a,
                            "收益率": profit_pct,
                            "Poly池": item['poly_liq'],
                            "Prob池": item['prob_liq'],
                            "理论容量": max_cap
                        })
                # 策略 B
                if item['poly_no'] > 0 and item['prob_yes'] > 0:
                    cost_b = item['poly_no'] + item['prob_yes']
                    if cost_b < threshold_cost:
                        profit_pct = (1 - cost_b) / cost_b
                        max_cap = min(item['poly_liq'], item['prob_liq'])
                        arb_opportunities.append({
                            "市场": item['question'],
                            "策略": "🔵Poly(No) + 🟠Prob(Yes)",
                            "成本": cost_b,
                            "收益率": profit_pct,
                            "Poly池": item['poly_liq'],
                            "Prob池": item['prob_liq'],
                            "理论容量": max_cap
                        })

        if arb_opportunities:
            arb_df = pd.DataFrame(arb_opportunities)
            arb_df = arb_df.sort_values(by="收益率", ascending=False)
            
            st.info(f"💡 在 {min_profit}% 利润门槛下，发现 {len(arb_df)} 个套利机会！(总成本 < ${threshold_cost:.3f})")
            
            # 使用基础 Pandas Styler (不含 matplotlib 依赖)
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
                    "策略": st.column_config.TextColumn("套利策略", help="如何操作：在哪个平台买Yes，哪个买No"),
                    "理论容量": st.column_config.NumberColumn("理论容量 (基于流动性)", help="受限于两边市场中流动性较小的一方"),
                }
            )
        else:
            st.warning(f"🤷‍♂️ 在当前 {min_profit}% 利润要求下，未发现套利机会。试着调低一点阈值？")

else:
    with col_search:
        st.info("👈 请点击右侧的 '刷新数据' 按钮开始抓取。")
