import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="Probable API 结构透视", layout="wide")
st.title("🔬 Probable 原始数据透视镜")

# 只抓取 Probable 数据
@st.cache_data(ttl=600)
def get_probable_markets_raw():
    url = "https://market-api.probable.markets/public/api/v1/markets/"
    markets = []
    page = 1
    try:
        # 只抓前 5 页，足够找到活跃市场
        while page <= 5:
            resp = requests.get(url, params={"page": page, "limit": 100, "active": "true"}, timeout=5)
            if resp.status_code != 200: break
            data = resp.json()
            new = data.get("markets", []) 
            if not new: break
            markets.extend(new)
            page += 1
    except Exception as e:
        st.error(f"Error: {e}")
    return markets

markets = get_probable_markets_raw()
st.write(f"已获取 {len(markets)} 个 Probable 市场")

# 搜索框
search_term = st.text_input("🔍 输入市场名称关键词 (例如: Rainbow, FDV)", "")

if search_term:
    # 筛选
    filtered = [m for m in markets if search_term.lower() in m.get("question", "").lower()]
    
    if filtered:
        st.success(f"找到 {len(filtered)} 个相关市场")
        
        for m in filtered:
            with st.expander(f"📂 市场: {m.get('question')} (ID: {m.get('id')})", expanded=True):
                # 1. 打印 Question 和 Outcomes
                st.markdown(f"**Question:** {m.get('question')}")
                st.markdown(f"**Outcomes Raw:** `{m.get('outcomes')}`")
                
                # 2. 重点：打印 Tokens 列表
                st.markdown("### 🔑 Tokens 列表 (关键数据)")
                tokens = m.get("tokens", [])
                
                # 格式化显示 Token 信息
                token_data = []
                for t in tokens:
                    token_data.append({
                        "Token ID": t.get("token_id"),
                        "Outcome": t.get("outcome"),
                        "Name": t.get("name") # 有时候名称在这里
                    })
                
                st.table(pd.DataFrame(token_data))
                
                # 3. 完整原始 JSON (备查)
                st.json(m)
    else:
        st.warning("未找到匹配的市场")
