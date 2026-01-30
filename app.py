import streamlit as st
import requests
import re
import pandas as pd
from collections import defaultdict
from typing import Set, List, Dict, Optional

# ────────────────────────────────────────────────
# 页面设置 - 美化主题
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市场对比工具",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义 CSS 美化
st.markdown("""
    <style>
    .stExpander { border: 1px solid #ddd; border-radius: 8px; margin-bottom: 16px; background-color: #f9f9f9; }
    .stExpander > div > button { font-size: 18px !important; font-weight: bold; }
    .card { padding: 16px; border-radius: 12px; border: 1px solid #e0e0e0; background-color: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Polymarket vs Probable 相同市场名称对比工具")
st.markdown("自动找出两个平台完全相同的市场，并将变体（金额/日期/时间不同）归类显示")

# ────────────────────────────────────────────────
# 数据拉取函数（缓存完整市场列表）
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_polymarket_markets() -> List[Dict]:
    with st.spinner("正在从 Polymarket 拉取市场数据..."):
        base_url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "closed": "false", "limit": 1000, "offset": 0}
        markets = []
        while True:
            try:
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                markets.extend(data)
                params["offset"] += params["limit"]
            except Exception as e:
                st.error(f"Polymarket 拉取失败：{e}")
                return []
        return markets

@st.cache_data(ttl=300)
def get_probable_markets() -> List[Dict]:
    with st.spinner("正在从 Probable 拉取市场数据..."):
        base_url = "https://market-api.probable.markets/public/api/v1/markets/"
        markets = []
        page = 1
        limit = 100
        while True:
            try:
                params = {"page": page, "limit": limit, "active": "true"}
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                new_markets = data.get("markets", [])
                if not new_markets:
                    break
                markets.extend(new_markets)
                page += 1
            except Exception as e:
                st.error(f"Probable 拉取失败：{e}")
                return []
        return markets

# ────────────────────────────────────────────────
# 字符串清理 fallback
# ────────────────────────────────────────────────
def clean_for_grouping(q: str) -> str:
    q = q.lower().strip()
    q = re.sub(r'\?$', '', q)
    q = re.sub(r'^will\s+', '', q, flags=re.IGNORECASE)
    # 移除价格范围
    q = re.sub(r'\$\d{1,3}(?:,\d{3})*-\$\d{1,3}(?:,\d{3})*', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\$\d+(?:\.\d+)?[mkb]?', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\bone day after launch\b', '', q, flags=re.IGNORECASE)
    patterns = [
        r'\b(by|before|end of|signed by|settle at -|market cap / fdv >)\b\s*[\w\s\d,:\-]*',
        r'\b(march|december|january|super bowl lx|2026|2027|fifa world cup|gta vi)\b\s*[\w\s\d,]*',
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE)
    q = re.sub(r'\s+', ' ', q).strip(' -(),')
    return q if q else "uncategorized"

# ────────────────────────────────────────────────
# 智能分组：优先 event_id / category，fallback 字符串清理
# ────────────────────────────────────────────────
def group_markets(markets: List[Dict], platform: str) -> Dict[str, List[Dict]]:
    groups = defaultdict(list)
    for m in markets:
        # 优先用 event_id 或 event
        key = m.get('event_id') or m.get('event') or m.get('category', '') + '_' + m.get('subcategory', '')
        if not key or key == '_':  # fallback 字符串清理
            key = clean_for_grouping(m.get('question', ''))
        groups[key].append(m)
    return groups

# ────────────────────────────────────────────────
# 使用 session_state 持久化数据
# ────────────────────────────────────────────────
if 'poly_markets' not in st.session_state:
    st.session_state.poly_markets = []
if 'prob_markets' not in st.session_state:
    st.session_state.prob_markets = []
if 'common_groups' not in st.session_state:
    st.session_state.common_groups = {}

# 模糊搜索框 - 放在最上方
st.subheader("模糊搜索市场（实时搜索所有共同市场）")
search_query = st.text_input("输入市场名称关键词（忽略大小写，支持模糊匹配）", key="global_search")

# 按钮触发数据拉取和分组
if st.button("开始对比并显示结果（约 10–30 秒）", type="primary", use_container_width=True):
    st.session_state.poly_markets = get_polymarket_markets()
    st.session_state.prob_markets = get_probable_markets()

    col1, col2 = st.columns(2)
    col1.metric("Polymarket 活跃市场", len(st.session_state.poly_markets))
    col2.metric("Probable 活跃市场", len(st.session_state.prob_markets))

    # 共同市场：基于 question 匹配
    poly_questions = {m.get("question", "").strip().lower(): m for m in st.session_state.poly_markets}
    prob_questions = {m.get("question", "").strip().lower(): m for m in st.session_state.prob_markets}
    common_questions = set(poly_questions).intersection(prob_questions)
    common_poly = [poly_questions[q] for q in common_questions]
    common_prob = [prob_questions[q] for q in common_questions]

    # 智能分组：结合两个平台的 groups
    poly_groups = group_markets(common_poly, "poly")
    prob_groups = group_markets(common_prob, "prob")
    # 合并：用 key 作为共同组
    common_groups = {}
    for key in set(poly_groups).intersection(prob_groups):
        common_groups[key] = poly_groups[key] + prob_groups[key]  # 合并变体
    st.session_state.common_groups = common_groups

    if common_questions:
        st.success(f"找到 {len(common_questions)} 个完全相同的市场，已自动归类为 {len(st.session_state.common_groups)} 组")
    else:
        st.warning("目前没有完全相同的市场名称。")

# ────────────────────────────────────────────────
# 显示部分（使用 session_state 中的数据）
# ────────────────────────────────────────────────
if st.session_state.common_groups:
    groups = st.session_state.common_groups

    # 统计卡片
    group_sizes = [len(items) for items in groups.values()]
    st.subheader("总结统计")
    cols = st.columns(3)
    cols[0].metric("总组数", len(groups))
    cols[1].metric("最大组变体数", max(group_sizes) if group_sizes else 0)
    cols[2].metric("平均变体数/组", round(sum(group_sizes)/len(groups), 1) if groups else 0)

    # 最小变体数滑块
    min_variants = st.slider("显示组的最小变体数（1=显示所有组，包括单体）", min_value=1, max_value=10, value=2, step=1)

    # 先显示单体组（最前面）
    single_groups = {k: v for k, v in groups.items() if len(v) == 1}
    if single_groups and min_variants == 1:
        with st.expander(f"单体市场组（每个组仅1个市场，共 {len(single_groups)} 个）", expanded=False):
            all_singles = [item.get("question", "Unknown") for items in single_groups.values() for item in items]
            df_singles = pd.DataFrame({"市场名称": sorted(all_singles)})
            st.dataframe(df_singles, use_container_width=True, hide_index=True)

    st.subheader("归类结果")

    # 显示变体数 >= min_variants 的多变体组（不包含单体）
    multi_groups = {k: v for k, v in groups.items() if len(v) >= min_variants and len(v) > 1}
    for key, items in sorted(multi_groups.items(), key=lambda x: len(x[1]), reverse=True):
        with st.container():
            st.markdown(f'<div class="card">', unsafe_allow_html=True)
            title_cols = st.columns([5, 2])
            with title_cols[0]:
                st.markdown(f"**组：{key or '其他核心描述'}**")
            with title_cols[1]:
                size = len(items)
                if size >= 6:
                    st.success(f"{size} 个变体")
                elif size >= 4:
                    st.info(f"{size} 个变体")
                else:
                    st.warning(f"{size} 个变体")

            questions = [item.get("question", "Unknown") for item in items]
            df = pd.DataFrame({"完整市场名称": sorted(questions)})
            st.dataframe(df, use_container_width=True, hide_index=True, column_config={"完整市场名称": st.column_config.TextColumn(width="large")})

            st.markdown('</div>', unsafe_allow_html=True)

# 模糊搜索结果（独立实时显示）
if search_query and 'common_list' in st.session_state and st.session_state.common_list:
    search_query_lower = search_query.lower()
    matched = [q for q in st.session_state.common_list if search_query_lower in q]
    if matched:
        st.subheader(f"搜索结果：找到 {len(matched)} 个匹配的市场")
        df_matched = pd.DataFrame({"匹配市场名称": sorted(matched)})
        st.dataframe(df_matched, use_container_width=True, hide_index=True)
    else:
        st.warning("没有找到匹配的市场")

# ────────────────────────────────────────────────
# 页尾
# ────────────────────────────────────────────────
st.markdown("---")
st.caption("数据来源：Polymarket Gamma API & Probable Market Public API | 缓存 5 分钟")
