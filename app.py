import streamlit as st
import requests
import re
import pandas as pd
from collections import defaultdict
from typing import Set, List, Dict

# ────────────────────────────────────────────────
# 頁面設定 - 美化主題
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市場比對工具",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自訂 CSS 美化（讓 expander、表格更漂亮）
st.markdown("""
    <style>
    .stExpander {
        border: 1px solid #ddd;
        border-radius: 8px;
        margin-bottom: 16px;
        background-color: #f9f9f9;
    }
    .stExpander > div > button {
        font-size: 18px !important;
        font-weight: bold;
    }
    .card {
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        background-color: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Polymarket vs Probable 相同市場名稱比對工具")
st.markdown("自動找出兩個平台完全相同的市場，並將變體（金額/日期/時間不同）歸類顯示")

# ────────────────────────────────────────────────
# Polymarket 拉取
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_polymarket_questions() -> Set[str]:
    with st.spinner("正在從 Polymarket 拉取市場資料..."):
        base_url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "closed": "false", "limit": 1000, "offset": 0}
        questions: Set[str] = set()
        while True:
            try:
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                for market in data:
                    q = market.get("question", "").strip().lower()
                    if q:
                        questions.add(q)
                params["offset"] += params["limit"]
            except Exception as e:
                st.error(f"Polymarket 拉取失敗：{e}")
                return set()
        return questions

# ────────────────────────────────────────────────
# Probable 拉取
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_probable_questions() -> Set[str]:
    with st.spinner("正在從 Probable 拉取市場資料..."):
        base_url = "https://market-api.probable.markets/public/api/v1/markets/"
        questions: Set[str] = set()
        page = 1
        limit = 100
        while True:
            try:
                params = {"page": page, "limit": limit, "active": "true"}
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                markets = data.get("markets", [])
                pagination = data.get("pagination", {})

                for market in markets:
                    q = market.get("question", "").strip().lower()
                    if q:
                        questions.add(q)

                if not pagination.get("hasMore", False):
                    break
                page += 1
            except Exception as e:
                st.error(f"Probable 拉取失敗：{e}")
                return set()
        return questions

# ────────────────────────────────────────────────
# 字符串清理 → 分組 key
# ────────────────────────────────────────────────
def clean_for_grouping(q: str) -> str:
    q = q.lower().strip()
    q = re.sub(r'\?$', '', q)
    q = re.sub(r'\b(will|a token|during the|one day after launch|signed)\b', '', q, flags=re.IGNORECASE)
    q = re.sub(r'\$\d+(?:\.\d+)?[mkb]?', '', q, flags=re.IGNORECASE)
    patterns = [
        r'\b(by|before|end of|close above|fdv above|win the|album|perform|launch)\b\s*[\w\s\d,:\-]*',
        r'\b(march|december|january|super bowl lx|2026|2027|fifa world cup|gta vi)\b\s*[\w\s\d,]*',
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE)
    q = re.sub(r'\s+', ' ', q).strip(' -(),')
    return q if q else "uncategorized"


def group_by_cleaned_key(questions: List[str]) -> Dict[str, List[str]]:
    groups = defaultdict(list)
    for q in sorted(questions):
        key = clean_for_grouping(q)
        groups[key].append(q)
    return dict(groups)

# ────────────────────────────────────────────────
# 主邏輯
# ────────────────────────────────────────────────
if st.button("開始比對並顯示美化結果（約 10–30 秒）", type="primary", use_container_width=True):
    poly_questions = get_polymarket_questions()
    prob_questions = get_probable_questions()

    col1, col2 = st.columns(2)
    col1.metric("Polymarket 活躍市場", len(poly_questions))
    col2.metric("Probable 活躍市場", len(prob_questions))

    common = poly_questions.intersection(prob_questions)
    common_list = list(common)

    if common_list:
        st.success(f"找到 {len(common_list)} 個完全相同的市場，已自動歸類為 {len(groups)} 組")

        groups = group_by_cleaned_key(common_list)

        # 統計卡片
        group_sizes = [len(items) for items in groups.values()]
        st.subheader("總結統計")
        cols = st.columns(3)
        cols[0].metric("總組數", len(groups))
        cols[1].metric("最大組變體數", max(group_sizes) if group_sizes else 0)
        cols[2].metric("平均變體數/組", round(sum(group_sizes)/len(groups), 1) if groups else 0)

        st.subheader("歸類結果（只顯示 ≥2 個變體的組）")
        
        # 逐組顯示卡片
        for key, items in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
            if len(items) < 2:
                continue

            with st.container():
                st.markdown(f'<div class="card">', unsafe_allow_html=True)
                
                # 標題行
                title_cols = st.columns([5, 2])
                with title_cols[0]:
                    st.markdown(f"**組：{key or '其他核心描述'}**")
                with title_cols[1]:
                    size = len(items)
                    if size >= 6:
                        st.success(f"{size} 個變體")
                    elif size >= 4:
                        st.info(f"{size} 個變體")
                    else:
                        st.warning(f"{size} 個變體")

                # 表格顯示變體
                df = pd.DataFrame({"完整市場名稱": sorted(items)})
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={"完整市場名稱": st.column_config.TextColumn(width="large")}
                )

                st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.warning("目前沒有完全相同的市場名稱。")

# ────────────────────────────────────────────────
# 頁尾
# ────────────────────────────────────────────────
st.markdown("---")
st.caption("資料來源：Polymarket Gamma API & Probable Market Public API | 快取 5 分鐘 | 如需加入價格或其他功能，請提供下一步需求！")
