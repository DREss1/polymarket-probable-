import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import fuzz, process
from datetime import datetime, timezone

# --- 1. 核心过滤逻辑：确保市场“正活跃” ---
def is_truly_active(market_data):
    """
    不仅看 API 状态，还要看时间戳和流动性
    """
    now = datetime.now(timezone.utc)
    
    # 基础状态过滤
    if market_data.get('closed') is True or market_data.get('active') is False:
        return False
        
    # 时间戳过滤：如果已过结算时间，直接排除
    end_date_str = market_data.get('endDate') or market_data.get('end_date')
    if end_date_str:
        try:
            # 兼容多种 ISO 格式
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            if end_date < now: return False
        except: pass

    # 流动性过滤：无流动性的市场没有刷量价值
    liq = float(market_data.get('liquidity', 0))
    if liq < 50: # 过滤掉低于 $50 活力的僵尸市场
        return False
        
    return True

# --- 2. Polymarket 全量扫描 (基于 /events 接口) ---
def fetch_all_poly_active():
    """使用官方推荐的 /events 路径获取所有活跃市场"""
    all_active_markets = []
    offset = 0
    while True:
        # 强制 closed=false 获取未关闭事件
        url = f"https://gamma-api.polymarket.com/events?active=true&closed=false&limit=50&offset={offset}"
        try:
            resp = requests.get(url, timeout=10).json()
            if not resp or len(resp) == 0: break
            
            for event in resp:
                # 遍历事件下的所有具体市场
                for m in event.get('markets', []):
                    if is_truly_active(m):
                        all_active_markets.append({
                            "title": m['question'],
                            "yes_price": float(m.get('best_yes_price', 0.5)),
                            "liq": float(m.get('liquidity', 0)),
                            "url": f"https://polymarket.com/event/{m.get('slug')}"
                        })
            offset += 50
            if offset > 1000: break # 防止进入无限循环，Polymarket 活跃一般在千级
            time.sleep(0.1) # 遵守速率限制
        except: break
    return all_active_markets

# --- 3. Probable 全量扫描 (基于分页逻辑) ---
def fetch_all_prob_active():
    """根据你提供的 totalResults 字段进行地毯式扫描"""
    all_prob = []
    base_url = "https://market-api.probable.markets/public/api/v1/markets/"
    try:
        # 强制 closed=false 过滤
        params = {"active": "true", "closed": "false", "limit": 100, "page": 1}
        first = requests.get(base_url, params=params, timeout=10).json()
        
        # 获取总量并计算页数
        total = first.get('pagination', {}).get('totalResults', 0)
        for m in first.get('markets', []):
            if is_truly_active(m): all_prob.append(m)
            
        # 并发抓取剩余页码
        total_pages = (total // 100) + 1
        def fetch_p(p):
            p_params = {"active": "true", "closed": "false", "limit": 100, "page": p}
            return requests.get(base_url, params=p_params, timeout=10).json().get('markets', [])

        with ThreadPoolExecutor(max_workers=5) as exec:
            results = list(exec.map(fetch_p, range(2, total_pages + 1)))
        
        for r_list in results:
            for m in r_list:
                if is_truly_active(m): all_prob.append(m)
    except: pass
    return all_prob

# --- 4. 渲染界面与匹配 ---
# (此部分保留之前的侧边栏、匹配算法和表格显示逻辑)
