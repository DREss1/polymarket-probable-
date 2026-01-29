import streamlit as st
import requests
from typing import Set, List, Dict
from rapidfuzz import fuzz, process  # 用於模糊匹配分組

# ────────────────────────────────────────────────
# 頁面設定
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市場比對（支援歸類）",
    page_icon="🔍",
    layout="wide"
)

st.title("Polymarket vs Probable 相同市場名稱比對工具")
st.markdown("點擊按鈕從兩個平台拉取活躍市場，找出名稱完全相同的市場，並自動歸類相似變體（例如不同金額/日期的 FDV 市場）。")

# ────────────────────────────────────────────────
# Polymarket 函數（不變）
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
# Probable 函數（不變）
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
# 新增：分組函數（使用模糊匹配自動歸類）
# ────────────────────────────────────────────────
def group_similar_questions(questions: List[str], similarity_threshold: float = 85.0) -> Dict[str, List[str]]:
    """
    將相似問題分組。使用 rapidfuzz 計算相似度。
    - 先排序列表以便迭代。
    - 每個組用第一個問題作為 key（代表）。
    """
    if not questions:
        return {}

    sorted_questions = sorted(questions)  # 排序以便相似項相鄰
    groups: Dict[str, List[str]] = {}
    current_group_key = sorted_questions[0]
    groups[current_group_key] = [sorted_questions[0]]

    for q in sorted_questions[1:]:
        # 計算與當前組 key 的相似度
        similarity = fuzz.token_sort_ratio(current_group_key, q)
        if similarity >= similarity_threshold:
            groups[current_group_key].append(q)
        else:
            current_group_key = q
            groups[current_group_key] = [q]

    return groups

# ────────────────────────────────────────────────
# 主邏輯
# ────────────────────────────────────────────────
if st.button("開始比對並歸類市場（可能需要 10–30 秒）", type="primary", use_container_width=True):
    poly_questions = get_polymarket_questions()
    prob_questions = get_probable_questions()

    st.success(f"Polymarket 活躍市場數：{len(poly_questions)} 個")
    st.success(f"Probable 活躍市場數：{len(prob_questions)} 個")

    common = poly_questions.intersection(prob_questions)
    common_list = list(common)  # 轉 list 以便分組

    if common_list:
        st.subheader(f"找到 {len(common_list)} 個名稱完全相同的市場")
        
        # 自動分組
        groups = group_similar_questions(common_list, similarity_threshold=85.0)
        
        st.subheader(f"自動歸類結果（共 {len(groups)} 組，相似度閾值 85%）")
        for group_key, group_items in groups.items():
            with st.expander(f"組代表: {group_key}（{len(group_items)} 個變體）"):
                for item in sorted(group_items):
                    st.write(f"• {item}")
    else:
        st.warning("目前沒有完全相同的市場名稱。")

# 額外說明
st.markdown("---")
st.caption("資料來源：Polymarket Gamma API & Probable Market Public API | 快取 5 分鐘 | 歸類使用 rapidfuzz 模糊匹配（可調整閾值）")
