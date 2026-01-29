import requests
from typing import Set

# Polymarket: 获取 question set
def get_polymarket_questions() -> Set[str]:
    base_url = "https://gamma-api.polymarket.com/markets"
    params = {"active": "true", "closed": "false", "limit": 1000, "offset": 0}
    questions: Set[str] = set()
    while True:
        resp = requests.get(base_url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"Polymarket error {resp.status_code}: {resp.text}")
            break
        data = resp.json()
        if not isinstance(data, list) or not data:
            break
        for market in data:
            q = market.get("question", "").strip().lower()
            if q:
                questions.add(q)
        params["offset"] += params["limit"]
    print(f"Polymarket 活跃市场数量: {len(questions)}")
    return questions

# Probable: 获取 question set（使用 markets 端点）
def get_probable_questions() -> Set[str]:
    base_url = "https://market-api.probable.markets/public/api/v1/markets/"
    questions: Set[str] = set()
    page = 1
    limit = 100  # 最大100
    while True:
        params = {"page": page, "limit": limit, "active": "true"}
        # 可选加: "closed": "false" 如果需要严格活跃
        resp = requests.get(base_url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"Probable markets error {resp.status_code}: {resp.text}")
            break
        try:
            data = resp.json()
        except ValueError:
            print("Probable invalid JSON")
            break

        markets = data.get("markets", [])
        pagination = data.get("pagination", {})

        for market in markets:
            q = market.get("question", "").strip().lower()
            if q:
                questions.add(q)

        if not pagination.get("hasMore", False):
            break
        page += 1

    print(f"Probable 活跃市场数量: {len(questions)}")
    return questions

# 比较
poly_questions = get_polymarket_questions()
prob_questions = get_probable_questions()

common = poly_questions.intersection(prob_questions)

print(f"\n找到 {len(common)} 个名称完全相同的活跃市场（忽略大小写）：")
if common:
    for q in sorted(common):
        print(f"- {q}")
else:
    print("暂无完全匹配的市场。建议添加模糊匹配（例如使用 rapidfuzz 库）。")

# 可选：如果想模糊匹配，安装 rapidfuzz 后加这段
# from rapidfuzz import fuzz, process
# for p in poly_questions:
#     matches = process.extract(p, prob_questions, scorer=fuzz.token_sort_ratio, limit=3)
#     for match, score in matches:
#         if score > 85:
#             print(f"相似匹配 ({score}%): {p} → {match}")
