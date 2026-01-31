import streamlit as st
import requests
import pandas as pd
import json  # 新增引用

st.set_page_config(page_title="Polymarket vs Probable 市场对比", page_icon="📊", layout="wide")

st.title("Polymarket vs Probable 相同市场名称对比工具")
st.markdown("显示名称完全相同的市场，并附带流动性、成交量与 Polymarket 价格")

# 模糊搜索框
st.subheader("搜索市场")
search_query = st.text_input("输入关键词（忽略大小写）", key="search")

# 数据拉取
@st.cache_data(ttl=300)
def get_poly_markets():
    url = "https://gamma-api.polymarket.com/markets"
    # 增加 limit 防止分页过多，timeout 设大一点
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
            # 安全限制：防止循环过长
            if offset > 5000: break 
    except Exception as e:
        st.error(f"Polymarket 数据拉取失败: {e}")
    return markets

@st.cache_data(ttl=300)
def get_probable_markets():
    # 请根据你提供的 Probable 文档再次确认此 URL 是否正确
    # 通常可能是 /v1/markets 而不是 /public/api/v1/markets/
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    try:
        while True:
            resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=20)
            if resp.status_code != 200: break
            data = resp.json()
            # 根据文档结构调整 key，假设是 markets
            new = data.get("markets", []) 
            if not new: break
            markets.extend(new)
            page += 1
            if page > 50: break # 安全限制
    except Exception as e:
        st.error(f"Probable 数据拉取失败: {e}")
    return markets

# 初始化 Session State 用于存储结果，防止刷新丢失
if 'df_result' not in st.session_state:
    st.session_state.df_result = None

if st.button("开始对比（约 10–30 秒）", type="primary"):
    with st.spinner("正在从 Polymarket 和 Probable 拉取数据..."):
        poly = get_poly_markets()
        prob = get_probable_markets()

    if poly and prob:
        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}

        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))

        if not common_questions:
            st.warning("没有找到名称完全相同的市场")
        else:
            st.success(f"找到 {len(common_questions)} 个相同市场")

            rows = []
            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # --- 修复核心 bug 的代码 ---
                poly_price = "N/A"
                raw_prices = poly_m.get("outcomePrices", [])
                
                # 修复：如果 API 返回的是字符串形式的列表，进行解析
                if isinstance(raw_prices, str):
                    try:
                        prices = json.loads(raw_prices)
                    except:
                        prices = []
                else:
                    prices = raw_prices

                try:
                    yes = float(prices[0]) if len(prices) > 0 else 0
                    no = float(prices[1]) if len(prices) > 1 else 0
                    poly_price = f"Yes {yes:.1%} / No {no:.1%}"
                except (ValueError, TypeError, IndexError):
                    poly_price = "价格解析错误"
                # ---------------------------

                # Probable 流动性 & 成交量
                prob_liquidity = prob_m.get("liquidity", "N/A")
                prob_volume24 = prob_m.get("volume24hr", "N/A")

                rows.append({
                    "市场名称": poly_m["question"],
                    "Polymarket 价格": poly_price,
                    "Probable 流动性": prob_liquidity,
                    "Probable 24h 成交量": prob_volume24,
                })

            st.session_state.df_result = pd.DataFrame(rows)

# 显示结果逻辑
if st.session_state.df_result is not None:
    df = st.session_state.df_result
    
    # 执行过滤
    if search_query:
        filtered_df = df[df["市场名称"].str.contains(search_query, case=False, na=False)]
        st.subheader(f"搜索结果：{len(filtered_df)} 个")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("数据来源：Polymarket Gamma API & Probable Market Public API")
