import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API 路径 ---
st.set_page_config(page_title="2026 事件聚合对冲终端", layout="wide")
st.title("⚖️ 跨平台活跃市场监控 (事件归类/选项对比版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心逻辑：基于官方 Event Title 进行物理聚合 ---
def fetch_and_aggregate():
    # 结构: { "事件标题": { "选项名称": {"poly_price": 0, "prob_price": 0} } }
    event_registry = {} 
    status = st.sidebar.empty()
    
    # A. 抓取 Probable：利用其官方 event 字段作为“基准锚点”
    status.text("正在同步 Probable 官方事件流...")
    try:
        r = requests.get(f"{PROB_API}/markets/?active=true&closed=false&limit=100", timeout=10).json()
        for m in r.get('markets', []):
            # 获取父级事件名称
            event_obj = m.get('event', {})
            parent_title = event_obj.get('title') or m.get('question', '').split('?')[0]
            # 提取具体的子选项文字
            outcome_text = m.get('question', '').replace(parent_title, '').strip() or "默认/YES"
            
            if parent_title not in event_registry: event_registry[parent_title] = {}
            if outcome_text not in event_registry[parent_title]: event_registry[parent_title][outcome_text] = {"poly": 0, "prob": 0}
            
            event_registry[parent_title][outcome_text]["prob"] = float(m.get('yes_price', 0))
    except: pass

    # B. 抓取 Polymarket：通过标题包含逻辑进行对齐
    status.text("正在同步 Polymarket 并对齐子选项...")
    try:
        r = requests.get(f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100", timeout=10).json()
        for m in r:
            full_q = m.get('question', '').strip()
            # 寻找该 question 属于哪一个已注册的父级事件
            for parent in event_registry.keys():
                if parent in full_q:
                    outcome_text = full_q.replace(parent, '').strip() or "默认/YES"
                    # 如果该子选项在 Prob 注册过，则填入价格
                    if outcome_text in event_registry[parent]:
                        event_registry[parent][outcome_text]["poly"] = float(m.get('best_yes_price', 0))
    except: pass
    
    status.success("全量同步对齐完成！")
    return event_registry

# --- 3. 界面渲染：一个事件一个框，内部表格横向比对 ---
def render_monitor(keyword):
    events = fetch_and_aggregate()
    
    # 排序：按事件标题首字母
    sorted_parents = sorted(events.keys())

    for title in sorted_parents:
        # 关键词过滤
        if keyword and keyword.lower() not in title.lower():
            continue
            
        # 提取当前事件下所有对齐成功的选项
        rows = []
        for opt, prices in events[title].items():
            if prices['poly'] > 0 and prices['prob'] > 0: # 仅显示两边都有的有效对冲项
                rows.append({
                    "具体预测项 (选项)": opt,
                    "Polymarket 价格": f"${prices['poly']:.3f}",
                    "Probable 价格": f"${prices['prob']:.3f}",
                    "差价": round(abs(prices['poly'] - prices['prob']), 4)
                })
        
        # 只有当该事件下至少有一个成功对齐的选项时，才显示该折叠框
        if rows:
            with st.expander(f"📦 事件：{title}", expanded=True):
                st.table(pd.DataFrame(rows)) # 内部使用静态表格展现，禁止重复排列

# --- 4. 主界面 ---
st.sidebar.header("🔍 聚合设置")
search_kw = st.sidebar.text_input("搜索特定事件 (如 MegaETH)", "")
if st.sidebar.button("🚀 启动地毯式聚合扫描"):
    st.write(f"⏰ **实时对齐时间: {datetime.now().strftime('%H:%M:%S')}**")
    render_monitor(search_kw)
