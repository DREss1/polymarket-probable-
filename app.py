import streamlit as st
import requests
import pandas as pd

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
    params = {"active": "true", "closed": "false", "limit": 1000}
    markets = []
    offset = 0
    while True:
        resp = requests.get(url, params={**params, "offset": offset}, timeout=15)
        data = resp.json()
        if not data: break
        markets.extend(data)
        offset += 1000
    return markets

@st.cache_data(ttl=300)
def get_probable_markets():
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    while True:
        resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=15)
        data = resp.json()
        new = data.get("markets", [])
        if not new: break
        markets.extend(new)
        page += 1
    return markets

if st.button("开始对比（约 10–30 秒）", type="primary"):
    with st.spinner("拉取数据..."):
        poly = get_poly_markets()
        prob = get_probable_markets()

    poly_dict = {m["question"].strip().lower(): m for m in poly}
    prob_dict = {m["question"].strip().lower(): m for m in prob}

    common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))

    if not common_questions:
        st.warning("没有找到名称完全相同的市场")
    else:
        st.success(f"找到 {len(common_questions)} 个相同市场")

        rows = []
        for q in common_questions:
            poly_m = poly_dict[q]
            prob_m = prob_dict[q]

            # Polymarket 价格
            poly_price = "N/A"
            if "outcomePrices" in poly_m and poly_m["outcomePrices"]:
                prices = poly_m["outcomePrices"]
                yes = float(prices[0]) if len(prices) > 0 else 0
                no = float(prices[1]) if len(prices) > 1 else 0
                poly_price = f"Yes {yes:.1%} / No {no:.1%}"

            # Probable 流动性 & 成交量
            prob_liquidity = prob_m.get("liquidity", "N/A")
            prob_volume24 = prob_m.get("volume24hr", "N/A")

            rows.append({
                "市场名称": poly_m["question"],
                "Polymarket 价格": poly_price,
                "Probable 流动性": prob_liquidity,
                "Probable 24h 成交量": prob_volume24,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

# 实时搜索
if search_query and 'rows' in locals():
    filtered = [r for r in rows if search_query.lower() in r["市场名称"].lower()]
    if filtered:
        st.subheader(f"搜索结果：{len(filtered)} 个")
        st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)
    else:
        st.info("无匹配结果")

st.caption("数据来源：Polymarket Gamma API & Probable Market Public API | 缓存 5 分钟 | Probable 实时价格需 API Key")
