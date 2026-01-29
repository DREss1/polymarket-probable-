import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API 路径 ---
st.set_page_config(page_title="2026 市场聚合监控", layout="wide")
st.title("⚖️ 跨平台活跃市场监控 (分组聚合版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心抓取与结构化处理 ---
def fetch_and_group_data():
    poly_data = {}
    prob_data = {}
    status_msg = st.sidebar.empty()
    
    # A. 抓取 Polymarket 并按事件(Event)分组
    for i in range(5):
        status_msg.text(f"读取 Polymarket 第 {i+1} 页...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            for m in r:
                # 使用 event_id 或父级标题作为分组键
                parent_title = m.get('group_id') or m.get('question', '').split('?')[0] + '?'
                option_name = m.get('question', '').replace(parent_title, '').strip() or "主选项"
                
                if parent_title not in poly_data: poly_data[parent_title] = []
                poly_data[parent_title].append({
                    "选项": option_name,
                    "price": float(m.get('best_yes_price', 0))
                })
            time.sleep(0.1)
        except: break

    # B. 抓取 Probable 并按事件分组
    for i in range(1, 6):
        status_msg.text(f"读取 Probable 第 {i} 页...")
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            r = requests.get(url, timeout=10).json()
            markets = r.get('markets', [])
            if not markets: break
            for m in markets:
                # Probable 的 event_id 映射
                parent_title = m.get('question', '').split('?')[0] + '?'
                option_name = m.get('question', '').replace(parent_title, '').strip() or "主选项"
                
                if parent_title not in prob_data: prob_data[parent_title] = []
                prob_data[parent_title].append({
                    "选项": option_name,
                    "price": float(m.get('yes_price', 0))
                })
        except: break
        
    status_msg.success(f"同步完成！")
    return poly_data, prob_data

# --- 3. 匹配与展示逻辑 ---
def render_grouped_monitor(keyword):
    poly_groups, prob_groups = fetch_and_group_data()
    
    # 获取所有共同的父级标题并排序 [针对需求 2]
    common_titles = sorted([t for t in poly_groups if t in prob_groups])

    if not common_titles:
        st.warning("⚠️ 未发现标题匹配的活跃市场。")
        return

    for title in common_titles:
        # 关键词过滤
        if keyword and keyword.lower() not in title.lower():
            continue
            
        with st.expander(f"📦 核心事件：{title}", expanded=False):
            # 提取该事件下的所有选项进行对比
            p_options = {o['选项']: o['price'] for o in poly_groups[title]}
            b_options = {o['选项']: o['price'] for o in prob_groups[title]}
            
            comparison = []
            for opt in p_options:
                if opt in b_options:
                    comparison.append({
                        "具体选项/赔率项": opt,
                        "Polymarket 价": f"${p_options[opt]:.3f}",
                        "Probable 价": f"${b_options[opt]:.3f}",
                        "价差": round(abs(p_options[opt] - b_options[opt]), 4)
                    })
            
            if comparison:
                st.table(pd.DataFrame(comparison)) # 使用静态表格显示具体选项 [针对需求 3]
            else:
                st.write("该事件下暂无完全匹配的选项。")

# --- 4. 界面渲染 ---
st.sidebar.header("⚙️ 监控配置")
kw = st.sidebar.text_input("搜索事件关键词", "")
if st.sidebar.button("🚀 开始聚合扫描"):
    st.write(f"⏰ **数据同步时间: {datetime.now().strftime('%H:%M:%S')}**")
    render_grouped_monitor(kw)
