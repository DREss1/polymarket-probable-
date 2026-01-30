import streamlit as st
import requests
import pandas as pd

# ────────────────────────────────────────────────
# 页面设置 - 极简清爽风格
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 相同市场对比",
    page_icon="🔍",
    layout="wide"
)

# 简单 CSS：去除多余装饰，字体清晰
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3 { color: #333; }
    .stDataFrame { border: 1px solid #ddd; border-radius: 6px; }
    </style>
""", unsafe_allow_html=True)

st.title("Polymarket vs Probable 相同市场名称对比")
st.markdown("显示两个平台上**名称完全相同**的市场列表（忽略大小写）")

# ────────────────────────────────────────────────
# 数据拉取函数（缓存）
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_polymarket_questions() -> set:
    with st.spinner("正在从 Polymarket 拉取..."):
        base_url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "closed": "false", "limit": 1000, "offset": 0}
        questions = set()
        while True:
            try:
                resp = requests.get(base_url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                for m in data:
                    q = m.get("question", "").strip().lower()
                    if q:
                        questions.add(q)
                params["offset"] += params["limit"]
            except Exception as e:
                st.error(f"Polymarket 拉取失败：{e}")
                return set()
        return questions

@st.cache_data(ttl=300)
def get_probable_questions() -> set:
    with st.spinner("正在从 Probable 拉取..."):
        base_url = "https://market-api.probable.markets/public/api/v1/markets/"
        questions = set()
        page = 1
        limit = 100
        while True:
            try:
                params = {"page": page, "limit": limit, "active": "true"}
                resp = requests.get(base_url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                markets = data.get("markets", [])
                if not markets:
                    break
                for m in markets:
                    q = m.get("question", "").strip().lower()
                    if q:
                        questions.add(q)
                page += 1
            except Exception as e:
                st.error(f"Probable 拉取失败：{e}")
                return set()
        return questions

# ────────────────────────────────────────────────
# 模糊搜索框 - 放在最上方
# ────────────────────────────────────────────────
st.subheader("搜索共同市场")
search_query = st.text_input("输入关键词（忽略大小写，支持模糊匹配）", key="search_input")

# ────────────────────────────────────────────────
# 主逻辑：按钮触发对比
# ────────────────────────────────────────────────
if st.button("开始对比（约 10–30 秒）", type="primary"):
    poly_qs = get_polymarket_questions()
    prob_qs = get_probable_questions()

    col1, col2 = st.columns(2)
    col1.metric("Polymarket 活跃市场", len(poly_qs))
    col2.metric("Probable 活跃市场", len(prob_qs))

    common = poly_qs.intersection(prob_qs)
    common_list = sorted(common)

    if common_list:
        st.success(f"找到 {len(common_list)} 个名称完全相同的市场")

        # 直接显示表格
        df = pd.DataFrame({"市场名称": common_list})
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={"市场名称": st.column_config.TextColumn(width="large")}
        )
    else:
        st.warning("没有找到名称完全相同的市场")

# 实时模糊搜索结果（不依赖按钮）
if search_query:
    if 'common_list' in locals() and common_list:
        matched = [q for q in common_list if search_query.lower() in q]
        if matched:
            st.subheader(f"搜索结果：找到 {len(matched)} 个匹配")
            df_search = pd.DataFrame({"匹配市场名称": sorted(matched)})
            st.dataframe(df_search, use_container_width=True, hide_index=True)
        else:
            st.info("没有匹配结果")
    else:
        st.info("请先点击“开始对比”获取数据")

# ────────────────────────────────────────────────
# 页尾
# ────────────────────────────────────────────────
st.markdown("---")
st.caption("数据来源：Polymarket Gamma API & Probable Market Public API | 缓存 5 分钟")
