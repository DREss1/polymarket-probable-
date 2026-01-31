import streamlit as st
import requests
import pandas as pd
import json
import time

st.set_page_config(page_title="Polymarket vs Probable 市场对比", page_icon="📊", layout="wide")

st.title("Polymarket vs Probable 相同市场名称对比工具")
st.markdown("显示名称完全相同的市场，并附带双边价格、流动性与成交量对比")

# 模糊搜索框
st.subheader("搜索市场")
search_query = st.text_input("输入关键词（忽略大小写）", key="search")

# --- 1. 获取 Polymarket 市场列表 ---
@st.cache_data(ttl=300)
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

# --- 2. 获取 Probable 市场列表 (基础信息) ---
@st.cache_data(ttl=300)
def get_probable_markets():
    # 注意：这是 Public API，用于获取市场列表
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
    """
    根据文档：POST /public/api/v1/prices
    批量获取 Token 的 BUY 价格
    """
    if not token_ids:
        return {}
    
    # Orderbook API URL
    url = "https://api.probable.markets/public/api/v1/prices"
    results = {}
    
    # 分批处理，防止单次请求过大 (每次 50 个 Token)
    chunk_size = 50
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i+chunk_size]
        payload = [{"token_id": t, "side": "BUY"} for t in chunk]
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results.update(data)
        except Exception as e:
            print(f"Probable 价格获取失败 (Chunk {i}): {e}")
            
    return results

# 初始化 Session State
if 'df_result' not in st.session_state:
    st.session_state.df_result = None

if st.button("开始对比（约 10–30 秒）", type="primary"):
    with st.spinner("Step 1/3: 拉取 Polymarket 数据..."):
        poly = get_poly_markets()
    
    with st.spinner("Step 2/3: 拉取 Probable 市场列表..."):
        prob = get_probable_markets()

    if poly and prob:
        # 构建字典映射
        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}

        # 找到相同名称的市场
        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))

        if not common_questions:
            st.warning("没有找到名称完全相同的市场")
        else:
            # --- 提取 Token ID 并批量获取价格 ---
            with st.spinner(f"Step 3/3: 正在获取 {len(common_questions)} 个市场的 Probable 实时价格..."):
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
                
                # 调用批量价格接口
                price_data = get_probable_prices_batch(all_tokens_to_fetch)

            # --- 组装最终表格 ---
            rows = []
            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # 1. 处理 Polymarket 价格 (同时增加精度)
                poly_price_str = "N/A"
                raw_prices = poly_m.get("outcomePrices", [])
                if isinstance(raw_prices, str):
                    try:
                        prices = json.loads(raw_prices)
                    except:
                        prices = []
                else:
                    prices = raw_prices
                
                try:
                    p_yes = float(prices[0]) if len(prices) > 0 else 0
                    p_no = float(prices[1]) if len(prices) > 1 else 0
                    # 修改点：从 .0% 改为 .1% (保留1位小数)
                    poly_price_str = f"{p_yes:.1%} / {p_no:.1%}"
                except:
                    poly_price_str = "Err"

                # 2. 处理 Probable 价格
                prob_ids = prob_token_map.get(q, {})
                id_yes = prob_ids.get("Yes")
                id_no = prob_ids.get("No")
                
                prob_price_yes = price_data.get(id_yes, {}).get("BUY", "0") if id_yes else "0"
                prob_price_no = price_data.get(id_no, {}).get("BUY", "0") if id_no else "0"
                
                try:
                    pr_yes = float(prob_price_yes)
                    pr_no = float(prob_price_no)
                    # 修改点：从 .0% 改为 .1% (保留1位小数，例如 78.7%)
                    prob_price_str = f"{pr_yes:.1%} / {pr_no:.1%}"
                except:
                    prob_price_str = "N/A"

                # 3. Probable 其他数据
                prob_liq = float(prob_m.get("liquidity", 0))
                prob_vol = float(prob_m.get("volume24hr", 0))

                rows.append({
                    "市场名称": poly_m["question"],
                    "Poly 价格 (Y/N)": poly_price_str,
                    "Prob 价格 (Y/N)": prob_price_str,
                    "Prob 流动性": f"${prob_liq:,.0f}",
                    "Prob 24h量": f"${prob_vol:,.0f}",
                })

            st.session_state.df_result = pd.DataFrame(rows)
            st.success(f"对比完成！共找到 {len(common_questions)} 个相同市场。")

# 显示结果
if st.session_state.df_result is not None:
    df = st.session_state.df_result
    
    if search_query:
        filtered_df = df[df["市场名称"].str.contains(search_query, case=False, na=False)]
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("提示：价格格式为 'Yes概率 / No概率' (保留1位小数)。Probable 价格取自 Orderbook 的最佳买单 (Best Bid)。")
