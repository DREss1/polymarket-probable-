import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process # 换成高性能匹配库
from datetime import datetime

st.set_page_config(page_title="2026 极速对冲监控", layout="wide")
st.title("⚡ Polymarket & Probable 极速监控面板")

# --- 1. 并发抓取函数 ---
def fetch_url(url):
    try:
        return requests.get(url, timeout=5).json()
    except:
        return None

def get_all_data():
    urls = [
        "https://gamma-api.polymarket.com/markets?active=true&limit=100",
        "https://market-api.probable.markets/public/api/v1/markets/?active=true&limit=100"
    ]
    # 使用线程池并发抓取两个 API
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(fetch_url, urls))
    return results[0], results[1] # 返回 poly_raw, prob_raw

# --- 2. 高性能处理逻辑 ---
def fast_analyze(fuzz_threshold):
    poly_raw, prob_raw = get_all_data()
    
    if not poly_raw or not prob_raw:
        return pd.DataFrame()

    # 数据格式标准化 (基于 image_e2ff5d 和 image_e2fc97)
    poly_list = [{"title": m['question'], "liq": float(m.get('liquidity', 0))} for m in poly_raw if m.get('question')]
    # Probable 数据包裹在 markets 键下
    prob_list = [{"title": m['question'], "liq": float(m.get('liquidity', 0))} for m in prob_raw.get('markets', []) if m.get('question')]

    st.sidebar.write(f"Poly: {len(poly_list)} | Prob: {len(prob_list)}")

    matches = []
    # 提取所有标题进行批量匹配
    prob_titles = [m['title'] for m in prob_list]
    
    for p in poly_list:
        # 使用 rapidfuzz 的 extractOne 进行快速检索
        best_match = process.extractOne(p['title'], prob_titles, scorer=fuzz.token_set_ratio)
        
        if best_match and best_match[1] >= fuzz_threshold:
            b = prob_list[best_match[2]] # 获取匹配到的 Prob 市场对象
            matches.append({
                "市场名称": p['title'],
                "匹配得分": round(best_match[1], 1),
                "深度(Poly)": p['liq'],
                "深度(Prob)": b['liq'],
                "更新时间": datetime.now().strftime("%H:%M:%S")
            })
            
    return pd.DataFrame(matches)

# --- 3. 界面显示 ---
st.sidebar.header("性能控制")
fuzz_score = st.sidebar.slider("匹配精度", 50, 95, 70)

placeholder = st.empty()
while True:
    start_time = time.time()
    df = fast_analyze(fuzz_score)
    duration = time.time() - start_time
    
    with placeholder.container():
        st.write(f"⏱️ 本轮扫描耗时: {duration:.2f} 秒") # 监控速度提升
        if not df.empty:
            st.dataframe(df.sort_values(by="深度(Poly)", ascending=False), use_container_width=True)
        else:
            st.info("扫描中，未发现重合市场...")
            
    time.sleep(10) # 速度提升后，刷新频率可以更高
    st.rerun()
