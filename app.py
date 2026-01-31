import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="Polymarket vs Probable 市场对比", page_icon="📊", layout="wide")

st.title("Polymarket vs Probable 相同市场名称对比工具")
st.markdown("显示名称完全相同的市场，并附带双边价格、流动性与成交量对比")

# --- 核心数据拉取函数 (保持不变，利用 cache 减少重复请求) ---
@st.cache_data(ttl=600) # 缓存时间延长到 10 分钟
def get_poly_markets():
    url = "https://gamma-api.polymarket.com/markets"
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
            if offset > 5000: break 
    except Exception as e:
        st.error(f"Polymarket 数据拉取失败: {e}")
    return markets

@st.cache_data(ttl=600)
def get_probable_markets():
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    try:
        while True:
            resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=20)
            if resp.status_code != 200: break
            data = resp.json()
            new = data.get("markets", []) 
            if not new: break
            markets.extend(new)
            page += 1
            if page > 50: break
    except Exception as e:
        st.error(f"Probable 列表拉取失败: {e}")
    return markets

def get_probable_prices_batch(token_ids):
    if not token_ids: return {}
    url = "https://api.probable.markets/public/api/v1/prices"
    results = {}
    chunk_size = 50
    for i in range(0, len(token_ids), chunk_size):
        chunk = token_ids[i:i+chunk_size]
        payload = [{"token_id": t, "side": "BUY"} for t in chunk]
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                results.update(resp.json())
        except Exception as e:
            print(f"Probable 价格获取失败: {e}")
    return results

# --- 核心逻辑：数据处理并存入 Session State ---
def load_and_process_data():
    """此函数只在点击按钮时运行，执行耗时的 API 请求和数据处理"""
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    try:
        # Step 1
        status_text.text("Step 1/3: 正在获取 Polymarket 数据...")
        poly = get_poly_markets()
        progress_bar.progress(33)
        
        # Step 2
        status_text.text("Step 2/3: 正在获取 Probable 数据...")
        prob = get_probable_markets()
        progress_bar.progress(66)

        if not poly or not prob:
            st.error("无法获取数据，请稍后重试。")
            return

        # 数据匹配处理
        poly_dict = {m["question"].strip().lower(): m for m in poly if "question" in m}
        prob_dict = {m["question"].strip().lower(): m for m in prob if "question" in m}
        common_questions = sorted(set(poly_dict.keys()) & set(prob_dict.keys()))

        if not common_questions:
            st.warning("没有找到名称完全相同的市场")
            st.session_state.master_df = pd.DataFrame() # 存空表
        else:
            # Step 3
            status_text.text(f"Step 3/3: 正在同步 {len(common_questions)} 个市场的实时价格...")
            
            # Probable Token ID 提取
            prob_token_map = {} 
            all_tokens_to_fetch = []
            for q in common_questions:
                prob_m = prob_dict[q]
                tokens = prob_m.get("tokens", [])
                yes_token = next((t["token_id"] for t in tokens if t.get("outcome") == "Yes"), None)
                no_token = next((t["token_id"] for t in tokens if t.get("outcome") == "No"), None)
                prob_token_map[q] = {"Yes": yes_token, "No": no_token}
                if yes_token: all_tokens_to_fetch.append(yes_token)
                if no_token: all_tokens_to_fetch.append(no_token)
            
            # 批量获取价格
            price_data = get_probable_prices_batch(all_tokens_to_fetch)
            progress_bar.progress(90)

            # 组装 DataFrame
            rows = []
            for q in common_questions:
                poly_m = poly_dict[q]
                prob_m = prob_dict[q]

                # Polymarket 价格解析
                poly_price_str = "N/A"
                raw_prices = poly_m.get("outcomePrices", [])
                if isinstance(raw_prices, str):
                    try: prices = json.loads(raw_prices)
                    except: prices = []
                else: prices = raw_prices
                
                try:
                    p_yes = float(prices[0]) if len(prices) > 0 else 0
                    p_no = float(prices[1]) if len(prices) > 1 else 0
                    poly_price_str = f"{p_yes:.1%} / {p_no:.1%}"
                except: poly_price_str = "Err"

                # Probable 价格解析
                prob_ids = prob_token_map.get(q, {})
                id_yes = prob_ids.get("Yes")
                id_no = prob_ids.get("No")
                prob_price_yes = price_data.get(id_yes, {}).get("BUY", "0") if id_yes else "0"
                prob_price_no = price_data.get(id_no, {}).get("BUY", "0") if id_no else "0"
                
                try:
                    pr_yes = float(prob_price_yes)
                    pr_no = float(prob_price_no)
                    prob_price_str = f"{pr_yes:.1%} / {pr_no:.1%}"
                except: prob_price_str = "N/A"

                prob_liq = float(prob_m.get("liquidity", 0))
                prob_vol = float(prob_m.get("volume24hr", 0))

                rows.append({
                    "市场名称": poly_m["question"],
                    "Poly 价格 (Y/N)": poly_price_str,
                    "Prob 价格 (Y/N)": prob_price_str,
                    "Prob 流动性": prob_liq, # 存数字，方便排序
                    "Prob 24h量": prob_vol  # 存数字，方便排序
                })

            # 存入 Session State
            st.session_state.master_df = pd.DataFrame(rows)
            status_text.success(f"数据加载完成！共找到 {len(common_questions)} 个相同市场。")
            progress_bar.empty()
            
    except Exception as e:
        st.error(f"发生错误: {e}")

# --- 页面 UI 布局 ---

# 1. 顶部控制区
col1, col2 = st.columns([1, 4])
with col1:
    # 只有点击这个按钮，才会触发 API 请求
    if st.button("🔄 刷新/加载数据", type="primary"):
        load_and_process_data()

# 2. 检查是否有数据
if 'master_df' in st.session_state and not st.session_state.master_df.empty:
    df = st.session_state.master_df
    
    # --- 解决问题 3：带预测提示的搜索 ---
    with col2:
        # 获取所有市场名称列表
        market_options = df["市场名称"].tolist()
        # 使用 selectbox 实现“提示/预测”功能
        # index=None 让它默认不选中，placeholder 提示用户输入
        selected_market = st.selectbox(
            "🔍 搜索市场 (输入关键词，支持自动联想)", 
            options=market_options,
            index=None,
            placeholder="输入例如 'Trump' 或 'Bitcoin'...",
            label_visibility="collapsed" # 隐藏 label 让布局更紧凑
        )

    # --- 解决问题 2：清空逻辑 ---
    # 如果用户选择了某个市场，就只显示那一行；否则显示全部
    if selected_market:
        filtered_df = df[df["市场名称"] == selected_market]
        st.info(f"已定位到市场：{selected_market}")
    else:
        filtered_df = df
        # 这里还可以加一个简单的文本过滤作为补充，如果你想要模糊匹配多个结果
        # text_filter = st.text_input("模糊筛选 (可选)")
        # if text_filter: filtered_df = df[df["市场名称"].str.contains(text_filter, case=False)]

    # 3. 数据展示
    # 使用 column_config 格式化数字，这样排序依然生效，但显示带 $
    st.dataframe(
        filtered_df, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Prob 流动性": st.column_config.NumberColumn(format="$%d"),
            "Prob 24h量": st.column_config.NumberColumn(format="$%d"),
        }
    )
    
    st.caption(f"当前显示: {len(filtered_df)} 条数据 (共 {len(df)} 条)")

else:
    st.info("👋 请点击左上角的 '刷新/加载数据' 按钮开始。")
    st.caption("提示：数据加载后将暂存在内存中，搜索时不会消耗 API 次数。")
