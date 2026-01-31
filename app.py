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

# --- 核心逻辑：加载并处理数据 + 套利计算 ---
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
            st.session_state.arb_df = pd.DataFrame()
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
            arb_opportunities = [] # 用于存储套利机会

            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # --- 1. 获取并清洗 Polymarket 数据 ---
                raw_prices = poly_m.get("outcomePrices", [])
                if isinstance(raw_prices, str):
                    try: prices = json.loads(raw_prices)
                    except: prices = []
                else: prices = raw_prices
                
                # 提取浮点数价格 (用于计算)
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

                # --- 2. 获取并清洗 Probable 数据 ---
                prob_ids = prob_token_map.get(q, {})
                id_yes = prob_ids.get("Yes")
                id_no = prob_ids.get("No")
                # API 返回的 BUY 价格即为我们买入的成本
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

                # --- 3. 填充主表数据 ---
                rows_data.append([
                    poly_m["question"],
                    poly_price_str, prob_price_str,
                    poly_liq, poly_vol,
                    prob_liq, prob_vol
                ])

                # --- 4. 🚀 套利检测逻辑 ---
                # 只有当两边价格都有效 (>0) 时才检测
                if poly_p_yes > 0 and prob_p_no > 0:
                    # 策略 A: Poly买Yes + Prob买No
                    cost_a = poly_p_yes + prob_p_no
                    if cost_a < 0.99: # 留 1% 的 buffer (手续费/滑点)
                        profit_pct = (1 - cost_a) / cost_a
                        max_cap = min(poly_liq, prob_liq) # 短板理论
                        arb_opportunities.append({
                            "市场": poly_m["question"],
                            "策略": "🔵Poly(Yes) + 🟠Prob(No)",
                            "成本": cost_a,
                            "收益率": profit_pct,
                            "Poly池": poly_liq,
                            "Prob池": prob_liq,
                            "理论容量": max_cap
                        })

                if poly_p_no > 0 and prob_p_yes > 0:
                    # 策略 B: Poly买No + Prob买Yes
                    cost_b = poly_p_no + prob_p_yes
                    if cost_b < 0.99:
                        profit_pct = (1 - cost_b) / cost_b
                        max_cap = min(poly_liq, prob_liq)
                        arb_opportunities.append({
                            "市场": poly_m["question"],
                            "策略": "🔵Poly(No) + 🟠Prob(Yes)",
                            "成本": cost_b,
                            "收益率": profit_pct,
                            "Poly池": poly_liq,
                            "Prob池": prob_liq,
                            "理论容量": max_cap
                        })

            # --- 保存主表 ---
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

            # --- 保存套利表 ---
            if arb_opportunities:
                st.session_state.arb_df = pd.DataFrame(arb_opportunities)
            else:
                st.session_state.arb_df = pd.DataFrame()
            
            status_text.success(f"数据加载完成！发现 {len(common_questions)} 个市场，其中 {len(arb_opportunities)} 个套利机会。")
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

    # --- 2. 主数据表 ---
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
    # 🚀 底部红色区域：套利机会监测
    # ==========================================
    st.markdown("---") # 分割线
    
    # 创建一个显眼的容器
    with st.container(border=True):
        st.subheader("🚀 套利机会扫描 (Arbitrage Opportunities)")
        
        if 'arb_df' in st.session_state and not st.session_state.arb_df.empty:
            arb_df = st.session_state.arb_df.copy()
            
            # 按收益率倒序排列（利润最高的排前面）
            arb_df = arb_df.sort_values(by="收益率", ascending=False)
            
            # 样式优化
            st.info(f"💡 发现 {len(arb_df)} 个潜在套利机会！(阈值：总成本 < $0.99)")
            
            # 格式化显示
            styled_arb = arb_df.style.format({
                "成本": "${:.3f}",         # 保留3位小数，看清微小差价
                "收益率": "+{:.1%}",      # 显示百分比
                "Poly池": "${:,.0f}",
                "Prob池": "${:,.0f}",
                "理论容量": "${:,.0f}"    # 重点关注
            }).background_gradient(
                subset=["收益率"], cmap="Greens" # 收益率越高越绿
            ).bar(
                subset=["理论容量"], color='#ffcdd2' # 容量用条形图显示
            )

            st.dataframe(
                styled_arb,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "策略": st.column_config.TextColumn("套利策略", help="如何操作：在哪个平台买Yes，哪个买No"),
                    "理论容量": st.column_config.NumberColumn("理论可套利金额 (容量)", help="受限于两边市场中流动性较小的一方 (短板效应)"),
                }
            )
            st.caption("⚠️ 风险提示：'理论容量' 基于流动性池估算，实际成交深度可能略低。建议小额测试。")
            
        else:
            st.success("✅ 当前暂无明显的无风险套利机会 (所有组合成本均 > $0.99)")

else:
    with col_search:
        st.info("👈 请点击右侧的 '刷新数据' 按钮开始抓取。")
