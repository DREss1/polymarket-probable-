import streamlit as st
import requests
import re
from typing import Set, List, Dict

# ────────────────────────────────────────────────
# 頁面設定
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市場比對（精確分組）",
    page_icon="🔍",
    layout="wide"
)

st.title("Polymarket vs Probable 相同市場名稱比對工具")
st.markdown("""
**功能**：
- 拉取兩個平台所有活躍市場
- 找出**名稱完全相同**的市場
- 使用**精確規則**自動歸類同一項目下的變體（金額/日期不同）
- 目前支援：FDV 類型（aztec/backpack 等）、日期類型（ai industry downturn 等）
""")

# ────────────────────────────────────────────────
# Polymarket 函數
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)  # 5 分鐘快取
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
# Probable 函數
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
# 精確正則分組規則
# ────────────────────────────────────────────────
def group_by_pattern(questions: List[str]) -> Dict[str, List[str]]:
    """
    使用精確正則規則分組：
    1. FDV 類型：提取項目名（如 aztec, backpack, extended）
    2. 日期類型：提取 by 前面的部分（如 ai industry downturn）
    其他未匹配的放到「其他」組
    """
    groups: Dict[str, List[str]] = {}
    other: List[str] = []

    # FDV 模式： {項目名} fdv above $xxx one day after launch?
    fdv_pattern = re.compile(
        r'^([a-z0-9]+(?:\s+[a-z0-9]+)*)\s+fdv above \$[\d,.]+[mkb]? one day after launch\?$',
        re.IGNORECASE
    )

    # 日期模式： {描述} by {月份} {日}, {年}?
    date_pattern = re.compile(
        r'^(.+?)\s+by\s+[a-z]+\s+\d{1,2},\s+\d{4}\?$',
        re.IGNORECASE
    )

    for q in sorted(questions):
        q_lower = q.strip().lower()

        # 優先 FDV
        fdv_match = fdv_pattern.match(q_lower)
        if fdv_match:
            prefix = fdv_match.group(1).strip()
            groups.setdefault(prefix, []).append(q)
            continue

        # 再試日期
        date_match = date_pattern.match(q_lower)
        if date_match:
            prefix = date_match.group(1).strip()
            groups.setdefault(prefix, []).append(q)
            continue

        # 其他
        other.append(q)

    if other:
        groups["其他（未匹配模式）"] = other

    return groups

# ────────────────────────────────────────────────
# 主邏輯 - 按鈕觸發
# ────────────────────────────────────────────────
if st.button("開始比對並精確分組（約 10–30 秒）", type="primary", use_container_width=True):
    poly_questions = get_polymarket_questions()
    prob_questions = get_probable_questions()

    st.success(f"Polymarket 活躍市場數：{len(poly_questions)} 個")
    st.success(f"Probable 活躍市場數：{len(prob_questions)} 個")

    common = poly_questions.intersection(prob_questions)
    common_list = list(common)

    if common_list:
        st.subheader(f"找到 {len(common_list)} 個名稱完全相同的市場")

        # 精確分組
        groups = group_by_pattern(common_list)

        st.subheader(f"精確規則歸類結果（共 {len(groups)} 組）")
        # 按變體數量降序顯示
        for group_key, group_items in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
            count = len(group_items)
            with st.expander(f"組: {group_key} （{count} 個變體）", expanded=count >= 3):
                for item in sorted(group_items):
                    st.write(f"• {item}")
    else:
        st.warning("目前沒有完全相同的市場名稱。")

# 說明
st.markdown("---")
st.caption("""
資料來源：Polymarket Gamma API & Probable Market Public API  
快取 5 分鐘 | 分組規則基於項目名完全相同（金額/日期為變量）  
如果有新模式未覆蓋，請提供例子，我會繼續擴充正則！
""")
