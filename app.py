import streamlit as st
import pandas as pd
from datetime import datetime, timezone

# --- 核心修复：URL 路由修正器 ---
def generate_safe_url(m, platform="poly"):
    """
    根据 2026 年最新路由规则动态修正链接
    """
    if platform == "poly":
        # 修正 1：Polymarket 必须跳转到 /event/ 路径
        slug = m.get('slug', '').strip()
        # 过滤掉 2020/2024 的历史脏数据，确保 slug 是 2026 格式
        if "2020" in slug or "2024" in slug:
            return "https://polymarket.com/"
        return f"https://polymarket.com/event/{slug}"
    
    else:
        # 修正 2：Probable 必须使用 API 返回的完整 market_slug
        # 部分市场需要拼接 id 参数才能跳过 404 页面
        m_slug = m.get('market_slug') or m.get('slug')
        m_id = m.get('id', '')
        if not m_slug: return "https://probable.markets/"
        
        # 自动补全 2026 语言环境参数，防止跳转回首页
        return f"https://probable.markets/markets/{m_slug}?id={m_id}&lang=zh-CN"

# --- 增强型过滤：只抓取“真”市场 ---
def is_truly_tradeable(m):
    """
    通过生命体征校验，剔除 404 市场
    """
    now = datetime.now(timezone.utc)
    # 规则 A：流动性必须 > 0 (僵尸市场 liquidity 必为 0)
    if float(m.get('liquidity', 0)) <= 0: return False
    
    # 规则 B：过滤过期的 ISO 时间戳
    end_date_str = m.get('endDate') or m.get('end_date')
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            if end_date < now: return False
        except: pass
        
    return True

# --- 渲染表格时应用新逻辑 ---
# 在你的主循环中，将 '去Poly' 和 '去Prob' 的赋值改为：
# "去Poly": generate_safe_url(p_market, "poly")
# "去Prob": generate_safe_url(b_market, "prob")
