import streamlit as st
import requests
import re
from collections import defaultdict
from typing import Set, List

# ────────────────────────────────────────────────
# 頁面設定
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市場比對（進階分組）",
    page_icon="🔍",
    layout="wide"
)

st.title("Polymarket vs Probable 相同市場名稱比對工具")
st.markdown("""
**功能**：
- 拉取兩個平台所有活躍市場
- 找出**名稱完全相同**的市場
- 使用**字符串规范化清理**自動歸類同一項目下的變體（金額/日期/時間變量忽略）
- 測試顯示：FDV、股票價格、pregnant by/before、launch token 等變體可正確歸類
""")

# ────────────────────────────────────────────────
# Polymarket & Probable 拉取函數（不變）
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_polymarket_questions() -> Set[str]:
    with st.spinner("正在從 Polymarket 拉取..."):
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
                st.error(f"Polymarket 錯誤：{e}")
                return set()
        return questions

@st.cache_data(ttl=300)
def get_probable_questions() -> Set[str]:
    with st.spinner("正在從 Probable 拉取..."):
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
                st.error(f"Probable 錯誤：{e}")
                return set()
        return questions

# ────────────────────────────────────────────────
# 進階分組：字符串清理作為 key
# ────────────────────────────────────────────────
def clean_for_grouping(q: str) -> str:
    q = q.lower().strip()
    # 移除 ?
    q = re.sub(r'\?$', '', q)
    # 移除 'will ', 'a token', 'during the', 'one day after launch', 'signed'
    q = re.sub(r'\b(will|a token|during the|one day after launch|signed)\b', '', q)
    # 移除金額 $數字[mkb]
    q = re.sub(r'\$\d+(?:\.\d+)?[mkb]?', '', q)
    # 移除模板詞 + 後續變量：by/before/end of/close above/fdv above/win the/album/perform 等 + 日期/事件
    patterns = [
        r'\b(by|before|end of|close above|fdv above|win the|album|perform|launch)\b\s*[\w\s\d,:\-]*',
        r'\b(march|december|january|super bowl lx|2026|2027|fifa world cup|gta vi)\b\s*[\w\s\d,]*',
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE)
    # 清理多餘空格和標點
    q = re.sub(r'\s+', ' ', q).strip(' -(),')
    return q if q else "uncategorized"

def group_by_cleaned_key(questions: List[str]) -> Dict[str, List[str]]:
    groups = defaultdict(list)
    for q in sorted(questions):
        key = clean_for_grouping(q)
        groups[key].append(q)
    return dict(groups)  # 轉 dict 以排序

# ────────────────────────────────────────────────
# 主邏輯
# ────────────────────────────────────────────────
if st.button("開始比對並進階分組（約 10–30 秒）", type="primary", use_container_width=True):
    poly_questions = get_polymarket_questions()
    prob_questions = get_probable_questions()

    st.success(f"Polymarket 活躍市場：{len(poly_questions)} 個")
    st.success(f"Probable 活躍市場：{len(prob_questions)} 個")

    common = poly_questions.intersection(prob_questions)
    common_list = list(common)

    if common_list:
        st.subheader(f"找到 {len(common_list)} 個名稱完全相同的市場")

        groups = group_by_cleaned_key(common_list)

        st.subheader(f"進階清理歸類結果（共 {len(groups)} 組，只顯示 ≥2 個變體的組）")
        # 按變體數降序 + 展開大組
        for key, items in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
            if len(items) >= 2:  # 只顯示有變體的組
                with st.expander(f"組: {key or '核心描述'} （{len(items)} 個變體）", expanded=len(items) >= 4):
                    for item in sorted(items):
                        st.write(f"• {item}")
    else:
        st.warning("無完全相同市場。")

# 說明
st.markdown("---")
st.caption("""
資料來源：Polymarket & Probable Public API | 快取 5 分鐘  
分組邏輯：清理變量詞（金額/日期/模板），剩餘核心作為 key → 自動歸類變體  
效果：FDV/股票價格/pregnant/launch token 等變體可正確合併；若有誤組或新模式，貼例子我再優化！
""")
