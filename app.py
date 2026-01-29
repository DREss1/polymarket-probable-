import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- 1. 基础配置与 API ---
st.set_page_config(page_title="2026 聚合监控终端", layout="wide")
st.title("⚖️ 跨平台活跃市场监控 (事件聚合/子项对比版)")

POLY_GAMMA = "https://gamma-api.polymarket.com"
PROB_API = "https://market-api.probable.markets/public/api/v1"

# --- 2. 核心逻辑：提取父级事件与子选项 ---
def fetch_and_aggregate():
    event_map = {} # 结构: { "Event Title": { "options": { "Outcome": {"poly": price, "prob": price} } } }
    status = st.sidebar.empty()
    
    # A. 抓取 Polymarket 并提取事件结构
    for i in range(5):
        status.text(f"同步 Polymarket 数据 (页 {i+1})...")
        url = f"{POLY_GAMMA}/markets?active=true&closed=false&limit=100&offset={i*100}"
        try:
            r = requests.get(url, timeout=10).json()
            if not r: break
            for m in r:
                # 逻辑：寻找父级标题。通常选项在标题中由问号或特定后缀区分
                full_q = m.get('question', '').strip()
                # 简单拆分：以问号为界，前面是事件，后面可能是选项
                parent = full_q.split('?')[0] + '?' if '?' in full_q else full_q
                outcome = full_q.replace(parent, '').strip() or "默认/YES"
                
                if parent not in event_map: event_map[parent] = {"poly_opts": {}, "prob_opts": {}}
                event_map[parent]["poly_opts"][outcome] = float(m.get('best_yes_price', 0))
            time.sleep(0.1)
        except: break

    # B. 抓取 Probable 并利用官方 event 字段对齐
    for i in range(1, 6):
        status.text(f"同步 Probable 数据 (页 {i})...")
        url = f"{PROB_API}/markets/?active=true&closed=false&limit=100&page={i}"
        try:
            r = requests.get(url, timeout=10).json()
            for m in r.get('markets', []):
                # 优先使用 API 返回的 event title
                event_obj = m.get('event', {})
                parent = event_obj.get('title') or m.get('question', '').split('?')[0] + '?'
                full_q = m.get('question', '').strip()
                outcome = full_q.replace(parent, '').strip() or "默认/YES"
                
                if parent not in event_map: event_map[parent] = {"poly_opts": {}, "prob_opts": {}}
                event_map[parent]["prob_opts"][outcome] = float(m.get('yes_price', 0))
        except: break
        
    status.success("全量同步完成！")
    return event_map

# --- 3. 渲染逻辑：仅显示两边都有的“事件” ---
def render_monitor(keyword):
    aggregated_data = fetch_and_aggregate()
    
    # 过滤：只有当一个事件在两边平台都有对应的子选项时才显示
    matched_events = []
    for title, data in aggregated_data.items():
        # 寻找重合的子选项名称
        poly_set = set(data['poly_opts'].keys())
        prob_set = set(data['prob_opts'].keys())
        common_outcomes = poly_set.intersection(prob_set)
        
        if common_outcomes:
            matched_events.append({"title": title, "outcomes": list(common_outcomes), "data": data})

    # 按事件标题排序
    matched_events = sorted(matched_events, key=lambda x: x['title'])

    for ev in matched_events:
        if keyword and keyword.lower() not in ev['title'].lower():
            continue
            
        with st.expander(f"📌 事件：{ev['title']}", expanded=True):
            comparison_rows = []
            for out in ev['outcomes']:
                comparison_rows.append({
                    "具体选项/赔率项": out,
                    "Polymarket 价格": f"${ev['data']['poly_opts'][out]:.3f}",
                    "Probable 价格": f"${ev['data']['prob_opts'][out]:.3f}",
                    "价差": round(abs(ev['data']['poly_opts'][out] - ev['data']['prob_opts'][out]), 4)
                })
            
            # 以表格形式展示该事件下所有匹配的子选项
            st.table(pd.DataFrame(comparison_rows))

# --- 4. 界面渲染 ---
st.sidebar.header("🔍 聚合监控配置")
search_kw = st.sidebar.text_input("搜索事件关键词 (如 MegaETH)", "")
if st.sidebar.button("🚀 开始聚合扫描"):
    st.write(f"⏰ **数据对齐时间: {datetime.now().strftime('%H:%M:%S')}**")
    render_monitor(search_kw)
