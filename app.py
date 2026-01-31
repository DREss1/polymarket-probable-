import streamlit as st
import requests
import pandas as pd
import json
import time

st.set_page_config(page_title="Polymarket vs Probable 市场对比 (Pro)", page_icon="🕵️", layout="wide")

st.title("🕵️ Polymarket vs Probable 套利侦探 (Debug Mode)")
st.markdown("⚠️ **高频模式**：已移除所有价格缓存，每次刷新都会请求最新 Orderbook。")

# --- Session State ---
if 'stats_poly_count' not in st.session_state: st.session_state['stats_poly_count'] = 0
if 'stats_prob_count' not in st.session_state: st.session_state['stats_prob_count'] = 0

# --- 辅助函数 ---
def safe_float(val):
    try:
        return float(val)
    except: return 0.0

def parse_outcomes(outcomes_str):
    default = ["Yes", "No"]
    if not outcomes_str: return default
    try:
        if isinstance(outcomes_str, str):
            data = json.loads(outcomes_str)
            if isinstance(data, list) and len(data) >= 2: return data
        elif isinstance(outcomes_str, list) and len(outcomes_str) >= 2:
            return outcomes_str
    except: pass
    return default

# --- 1. 获取市场列表 (结构缓存，价格不缓存) ---
@st.cache_data(ttl=300)
def get_market_structure():
    # Polymarket
    poly_url = "https://gamma-api.polymarket.com/markets"
    poly_params = {"active": "true", "closed": "false", "limit": 500}
    poly_markets = []
    offset = 0
    try:
        while True:
            resp = requests.get(poly_url, params={**poly_params, "offset": offset}, timeout=5)
            if resp.status_code != 200: break 
            data = resp.json()
            if not data: break
            poly_markets.extend(data)
            offset += 500
    except: pass

    # Probable
    prob_url = "https://market-api.probable.markets/public/api/v1/markets/"
    prob_markets = []
    page = 1
    try:
        while True:
            resp = requests.get(prob_url, params={"page": page, "limit": 100, "active": "true"}, timeout=5)
            if resp.status_code != 200: break
            data = resp.json()
            new = data.get("markets", []) 
            if not new: break
            prob_markets.extend(new)
            page += 1
    except: pass
    
    return poly_markets, prob_markets

# --- 2. 获取单个 Token 的 Orderbook (实时，无缓存) ---
def fetch_orderbook(platform, token_id):
    """
    获取真实的 Asks (卖单) 列表。
    返回格式: [{'price': float, 'size': float}, ...]
    """
    clean_asks = []
    raw_response = {} # 用于 Debug 显示
    
    if not token_id: return [], {}

    try:
        if platform == "Polymarket":
            url = f"https://clob.polymarket.com/book?token_id={token_id}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                raw_response = resp.json()
                asks = raw_response.get("asks", [])
                # Poly 格式: [{"price": "0.99", "size": "100"}]
                for item in asks:
                    clean_asks.append({
                        "price": float(item["price"]),
                        "size": float(item["size"])
                    })

        elif platform == "Probable":
            url = f"https://api.probable.markets/public/api/v1/book?token_id={token_id}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                raw_response = resp.json()
                asks = raw_response.get("asks", [])
                # Prob 格式: [["0.99", "100"], ...]
                for item in asks:
                    clean_asks.append({
                        "price": float(item[0]),
                        "size": float(item[1])
                    })
    except Exception as e:
        raw_response = {"error": str(e)}

    return clean_asks, raw_response

# --- 3. 计算真实可买入容量 ---
def calculate_real_capacity(poly_asks, prob_asks):
    """
    计算两边 Asks 的重叠容量。
    简单算法：只要价格合理 (Poly + Prob < 1.01)，就视为有效深度。
    """
    cap_poly = 0.0
    cap_prob = 0.0
    
    if poly_asks:
        best = poly_asks[0]['price']
        limit = best * 1.05 # 5% 滑点
        for a in poly_asks:
            if a['price'] > limit: break
            cap_poly += a['price'] * a['size']
            
    if prob_asks:
        best = prob_asks[0]['price']
        limit = best * 1.05
        for a in prob_asks:
            if a['price'] > limit: break
            cap_prob += a['price'] * a['size']
            
    return min(cap_poly, cap_prob)

# --- 主逻辑 ---
def main():
    col_ctrl, col_info = st.columns([1, 2])
    with col_ctrl:
        if st.button("🔄 刷新全量数据 (API)", type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    # 1. 加载结构
    with st.spinner("正在同步市场结构..."):
        poly_markets, prob_markets = get_market_structure()
        st.session_state['stats_poly_count'] = len(poly_markets)
        st.session_state['stats_prob_count'] = len(prob_markets)

    # 2. 匹配
    poly_dict = {m["question"].strip().lower(): m for m in poly_markets if "question" in m}
    prob_dict = {m["question"].strip().lower(): m for m in prob_markets if "question" in m}
    common_keys = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))
    
    st.info(f"🔍 找到 {len(common_keys)} 个同名市场。请在下方选择一个进行【深度侦探】。")

    # 3. 选择器
    selected_q = st.selectbox("选择要分析的市场:", common_keys, index=None)

    # 4. 深度分析视图
    if selected_q:
        st.divider()
        st.subheader(f"🔬 市场显微镜: {selected_q}")
        
        poly_m = poly_dict[selected_q]
        prob_m = prob_dict[selected_q]
        
        # --- 解析 ID ---
        # Probable IDs
        prob_tokens = prob_m.get("tokens", [])
        prob_yes_id = next((t["token_id"] for t in prob_tokens if t.get("outcome") == "Yes"), None)
        prob_no_id = next((t["token_id"] for t in prob_tokens if t.get("outcome") == "No"), None)
        
        # Polymarket IDs (严格匹配)
        poly_clob_ids = []
        if "clobTokenIds" in poly_m:
            raw_ids = poly_m["clobTokenIds"]
            poly_clob_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
        
        # ⚠️ 关键修正：确保 Poly ID 顺序正确
        # Poly API 的 outcomes 顺序通常对应 clobTokenIds 的顺序
        poly_outcomes = parse_outcomes(poly_m.get("outcomes"))
        poly_yes_id = None
        poly_no_id = None
        
        if len(poly_clob_ids) == len(poly_outcomes):
            for idx, out_name in enumerate(poly_outcomes):
                if out_name == "Yes": poly_yes_id = poly_clob_ids[idx]
                if out_name == "No": poly_no_id = poly_clob_ids[idx]
        else:
            # Fallback: 假设 [0] 是 Yes
            if len(poly_clob_ids) >= 2:
                poly_yes_id = poly_clob_ids[0]
                poly_no_id = poly_clob_ids[1]

        # --- 布局显示 ---
        col1, col2 = st.columns(2)
        
        # 左侧：Token ID 核对
        with col1:
            st.markdown("### 🆔 Token ID 核对")
            st.markdown("**Polymarket**")
            st.code(f"Yes ID: {poly_yes_id}\nNo  ID: {poly_no_id}")
            st.markdown("**Probable**")
            st.code(f"Yes ID: {prob_yes_id}\nNo  ID: {prob_no_id}")
            if not poly_yes_id or not prob_yes_id:
                st.error("⚠️ 警告：未能解析出完整的 Token ID，数据可能不准确。")

        # 右侧：实时 Orderbook 抓取
        with col2:
            st.markdown("### ⚡ 实时 Orderbook (Ask/卖一价)")
            
            # 只有点击按钮才抓取，省流
            if st.button("🚀 抓取实时深度数据"):
                # Fetch Data
                poly_yes_asks, poly_yes_raw = fetch_orderbook("Polymarket", poly_yes_id)
                poly_no_asks, poly_no_raw = fetch_orderbook("Polymarket", poly_no_id)
                prob_yes_asks, prob_yes_raw = fetch_orderbook("Probable", prob_yes_id)
                prob_no_asks, prob_no_raw = fetch_orderbook("Probable", prob_no_id)

                # Display Prices
                p_yes_price = poly_yes_asks[0]['price'] if poly_yes_asks else 0
                p_no_price = poly_no_asks[0]['price'] if poly_no_asks else 0
                pr_yes_price = prob_yes_asks[0]['price'] if prob_yes_asks else 0
                pr_no_price = prob_no_asks[0]['price'] if prob_no_asks else 0
                
                # Table
                data = {
                    "Outcome": ["Yes", "No"],
                    "Poly Best Ask ($)": [p_yes_price, p_no_price],
                    "Prob Best Ask ($)": [pr_yes_price, pr_no_price],
                }
                st.dataframe(pd.DataFrame(data), hide_index=True)
                
                # Debug Info Expander
                with st.expander("🔍 查看原始 API 返回数据 (Raw JSON)"):
                    st.write("Polymarket Yes Book:", poly_yes_raw)
                    st.write("Probable Yes Book:", prob_yes_raw)

                # Arb Calc
                cost_a = p_yes_price + pr_no_price
                cost_b = p_no_price + pr_yes_price
                
                st.markdown("### 💰 套利验算")
                if p_yes_price > 0 and pr_no_price > 0:
                    st.write(f"**策略 A (Poly Yes + Prob No):** 成本 ${cost_a:.4f}")
                    if cost_a < 1.0:
                        cap = calculate_real_capacity(poly_yes_asks, prob_no_asks)
                        st.success(f"✅ 发现机会！收益率: +{(1-cost_a)/cost_a:.1%} | 真实容量: ${cap:.2f}")
                    else:
                        st.warning("❌ 无机会 (成本 > $1.0)")
                
                if p_no_price > 0 and pr_yes_price > 0:
                    st.write(f"**策略 B (Poly No + Prob Yes):** 成本 ${cost_b:.4f}")
                    if cost_b < 1.0:
                        cap = calculate_real_capacity(poly_no_asks, prob_yes_asks)
                        st.success(f"✅ 发现机会！收益率: +{(1-cost_b)/cost_b:.1%} | 真实容量: ${cap:.2f}")
                    else:
                        st.warning("❌ 无机会 (成本 > $1.0)")

if __name__ == "__main__":
    main()
