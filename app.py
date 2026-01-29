import streamlit as st
import pandas as pd
import time
from datetime import datetime

# 页面配置
st.set_page_config(page_title="2026 预测市场对冲监控", layout="wide")
st.title("📊 Polymarket & Probable 实时监控面板")

# 1. 模拟数据获取（确保这里的“键”和后面调用的一致）
def get_market_data():
    data = [
        {"市场名称": "BTC 年底是否站上 100k?", "无损成本": 0.991, "深度($)": 52000, "24h成交量": 1200000},
        {"市场名称": "BNB Chain 交易量突破预测", "无损成本": 1.005, "深度($)": 15000, "24h成交量": 450000},
        {"市场名称": "以太坊 3月 升级是否按时", "无损成本": 0.998, "深度($)": 85000, "24h成交量": 2100000}
    ]
    return pd.DataFrame(data)

# 2. 侧边栏设置
st.sidebar.header("监控设置")
refresh_rate = st.sidebar.slider("自动刷新频率 (秒)", 5, 60, 10)
cost_limit = st.sidebar.number_input("成本阈值 (如 1.00 为绝对无损)", value=1.02, step=0.01)

# 3. 动态刷新逻辑
placeholder = st.empty()

while True:
    df = get_market_data()
    
    # 这里的列名必须和 get_market_data 里的完全一样！
    # 排序逻辑：深度 > 成交量
    df_filtered = df[df['无损成本'] <= cost_limit]
    df_sorted = df_filtered.sort_values(by=['深度($)', '24h成交量'], ascending=False)
    
    with placeholder.container():
        st.write(f"⏰ 最后更新时间: {datetime.now().strftime('%H:%M:%S')}")
        
        if not df_sorted.empty:
            # 展示表格
            st.dataframe(
                df_sorted.style.highlight_min(subset=['无损成本'], color='lightgreen'),
                use_container_width=True
            )
            # 套利机会提醒
            if any(df_sorted['无损成本'] < 1.0):
                st.success("🔥 发现套利机会（成本 < 1.0）！")
                st.balloons()
        else:
            st.warning("当前没有符合成本阈值的市场，请尝试调高侧边栏的‘成本阈值’。")

    time.sleep(refresh_rate)
    st.rerun()