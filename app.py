import streamlit as st
import requests
from typing import Set

# ────────────────────────────────────────────────
# 頁面設定（放在最上面）
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket vs Probable 市場名稱比對",
    page_icon="🔍",
    layout="wide"
)

st.title("Polymarket vs Probable 相同市場名稱比對工具")
st.markdown("點擊按鈕從兩個平台拉取活躍市場，找出名稱完全相同的市場（忽略大小寫）")

# ────────────────────────────────────────────────
# Polymarket 函數
# ────────────────────────────────────────────────
@st.cache_data(ttl=300)  # 快取 5 分鐘，避免一直打 API
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
# 主邏輯 - 按鈕觸發
# ────────────────────────────────────────────────
if st.button("開始比對市場（可能需要 10–30 秒）", type="primary", use_container_width=True):
    poly_questions = get_polymarket_questions()
    prob_questions = get_probable_questions()

    st.success(f"Polymarket 活躍市場數：{len(poly_questions)} 個")
    st.success(f"Probable 活躍市場數：{len(prob_questions)} 個")

    common = poly_questions.intersection(prob_questions)

    if common:
        st.subheader(f"找到 {len(common)} 個名稱完全相同的市場")
        with st.expander("點擊展開完整清單（排序後）"):
            for q in sorted(common):
                st.write(f"• {q}")
    else:
        st.warning("目前沒有完全相同的市場名稱。")
        st.info("可能原因：兩個平台市場命名風格不同。可以考慮加入模糊匹配功能。")

# 額外說明
st.markdown("---")
st.caption("資料來源：Polymarket Gamma API & Probable Market Public API | 快取 5 分鐘 | 如有錯誤請檢查網路或 API 是否變更")
