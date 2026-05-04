#!/usr/bin/env python3
"""
Apple 台灣 新品 & 整修品追蹤器 v2
- 每日檢查新品配件 + 整修品
- Discord 通知含商品圖片
- 每週一自動發送本週新品彙整
"""

import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── 設定區 ───────────────────────────────────────────────────────
ACCESSORIES_URL = "https://www.apple.com/tw/shop/accessories/all/new-arrivals"
REFURBISHED_URL = "https://www.apple.com/tw/shop/refurbished"

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "your_discord_webhook_url_here")

SNAPSHOT_FILE    = Path("snapshot.json")
WEEKLY_LOG_FILE  = Path("weekly_log.json")
# ──────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}


# ── 抓取頁面 ──────────────────────────────────────────────────────

def fetch_items(url: str, label: str) -> dict:
    """通用抓取函式，回傳 {name: {price, link, image}}"""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = {}

    # 嘗試多種常見 Apple 商品卡片 selector
    cards = soup.select(
        "[class*='productitem'], [class*='product-item'], "
        "[class*='rf-product'], [class*='refurbished-product']"
    )

    for card in cards:
        name_tag  = card.select_one("[class*='title'], h3, h2, h4")
        price_tag = card.select_one("[class*='price'], [class*='currentprice']")
        link_tag  = card.select_one("a[href]")
        img_tag   = card.select_one("img[src]")

        if not name_tag:
            continue

        name  = name_tag.get_text(strip=True)
        price = price_tag.get_text(strip=True) if price_tag else "N/A"
        link  = ("https://www.apple.com" + link_tag["href"]) if link_tag else ""

        # 圖片：優先用 srcset 最後一張（最高解析），否則用 src
        image = ""
        if img_tag:
            srcset = img_tag.get("srcset", "")
            if srcset:
                # srcset 格式：url 1x, url 2x ...
                last = srcset.strip().split(",")[-1].strip().split(" ")[0]
                image = last if last.startswith("http") else "https://www.apple.com" + last
            else:
                src = img_tag.get("src", "")
                image = src if src.startswith("http") else "https://www.apple.com" + src

        if name:
            items[name] = {
                "price": price,
                "link": link,
                "image": image,
                "source": label,
            }

    return items


# ── 快照管理 ──────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 週記錄管理 ────────────────────────────────────────────────────

def update_weekly_log(new_items: dict):
    """把本次新品加進週記錄"""
    log = load_json(WEEKLY_LOG_FILE)
    today = date.today().isoformat()
    if today not in log:
        log[today] = {}
    log[today].update(new_items)
    save_json(WEEKLY_LOG_FILE, log)


def get_weekly_items() -> dict:
    """取得本週（過去 7 天）所有新品"""
    log = load_json(WEEKLY_LOG_FILE)
    all_items = {}
    for day_items in log.values():
        all_items.update(day_items)
    return all_items


def clear_weekly_log():
    save_json(WEEKLY_LOG_FILE, {})


# ── Discord 發送 ──────────────────────────────────────────────────

def post_discord(payload: dict):
    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    if resp.status_code in (200, 204):
        print("✅ Discord 推播成功")
    else:
        print(f"⚠️  Discord 推播失敗：{resp.status_code} {resp.text}")


def send_new_items(new_accessories: dict, new_refurbished: dict, total_acc: int, total_ref: int):
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    all_new = {**new_accessories, **new_refurbished}

    if not all_new:
        # 沒有新品：灰色狀態通知
        payload = {
            "embeds": [{
                "title": "🔍 Apple 追蹤器 — 今日檢查完成",
                "description": (
                    f"**無新品上架**　|　{now}\n"
                    f"配件頁：{total_acc} 項　|　整修品：{total_ref} 項"
                ),
                "color": 0x95a5a6,
                "footer": {"text": "Apple 追蹤器　|　每日自動檢查"},
            }]
        }
        post_discord(payload)
        return

    # 有新品：每項商品獨立一則 embed（含圖片）
    embeds = []

    for name, info in list(all_new.items())[:10]:  # Discord 單次最多 10 個 embed
        source_label = "🆕 新品配件" if info.get("source") == "accessories" else "♻️ 整修品"
        embed = {
            "title": name,
            "url": info.get("link", ACCESSORIES_URL),
            "description": f"{source_label}　|　**{info.get('price', 'N/A')}**",
            "color": 0x000000 if info.get("source") == "accessories" else 0x2ecc71,
            "footer": {"text": f"Apple 追蹤器　|　{now}"},
        }
        if info.get("image"):
            embed["thumbnail"] = {"url": info["image"]}
        embeds.append(embed)

    # 第一則加上標題說明
    embeds[0]["title"] = f"🍎 {name}"  # 覆蓋第一則標題（保留商品名）
    payload = {
        "content": f"🍎 **Apple 新上架** — 共 {len(all_new)} 項新品　|　{now}",
        "embeds": embeds,
    }
    post_discord(payload)

    # 若超過 10 項，補發剩餘
    if len(all_new) > 10:
        remaining = list(all_new.items())[10:]
        extra_embeds = []
        for name, info in remaining:
            source_label = "🆕 新品配件" if info.get("source") == "accessories" else "♻️ 整修品"
            embed = {
                "title": name,
                "url": info.get("link", ACCESSORIES_URL),
                "description": f"{source_label}　|　**{info.get('price', 'N/A')}**",
                "color": 0x000000 if info.get("source") == "accessories" else 0x2ecc71,
            }
            if info.get("image"):
                embed["thumbnail"] = {"url": info["image"]}
            extra_embeds.append(embed)
        post_discord({"embeds": extra_embeds})


def send_weekly_summary():
    """每週一發送本週彙整"""
    weekly = get_weekly_items()
    now = datetime.now().strftime("%Y/%m/%d")

    if not weekly:
        payload = {
            "embeds": [{
                "title": "📋 Apple 追蹤器 — 本週彙整",
                "description": f"本週（截至 {now}）**無新品上架**",
                "color": 0x95a5a6,
                "footer": {"text": "Apple 追蹤器　|　每週彙整"},
            }]
        }
    else:
        acc_items = {k: v for k, v in weekly.items() if v.get("source") == "accessories"}
        ref_items = {k: v for k, v in weekly.items() if v.get("source") == "refurbished"}

        lines_acc = "\n".join([f"• [{n}]({i['link']})　{i['price']}" for n, i in acc_items.items()]) or "無"
        lines_ref = "\n".join([f"• [{n}]({i['link']})　{i['price']}" for n, i in ref_items.items()]) or "無"

        payload = {
            "embeds": [{
                "title": "📋 Apple 追蹤器 — 本週新品彙整",
                "description": f"本週共 **{len(weekly)}** 項新品　|　截至 {now}",
                "color": 0x3498db,
                "fields": [
                    {"name": f"🆕 新品配件（{len(acc_items)} 項）", "value": lines_acc[:1000], "inline": False},
                    {"name": f"♻️ 整修品（{len(ref_items)} 項）",   "value": lines_ref[:1000], "inline": False},
                ],
                "footer": {"text": "Apple 追蹤器　|　每週彙整"},
            }]
        }

    post_discord(payload)
    clear_weekly_log()
    print("✅ 週報已發送，週記錄已清空")


# ── 主流程 ────────────────────────────────────────────────────────

def main():
    today = date.today()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{now_str}] 開始檢查...")

    # 每週一（weekday=0）先發週報
    if today.weekday() == 0:
        print("📋 今天是週一，發送週報...")
        send_weekly_summary()

    # 抓配件新品
    try:
        accessories = fetch_items(ACCESSORIES_URL, "accessories")
        print(f"   配件頁：{len(accessories)} 項")
    except Exception as e:
        print(f"❌ 配件頁抓取失敗：{e}")
        accessories = {}

    # 抓整修品
    try:
        refurbished = fetch_items(REFURBISHED_URL, "refurbished")
        print(f"   整修品：{len(refurbished)} 項")
    except Exception as e:
        print(f"❌ 整修品抓取失敗：{e}")
        refurbished = {}

    # 比對快照
    snapshot = load_json(SNAPSHOT_FILE)
    prev_acc = snapshot.get("accessories", {})
    prev_ref = snapshot.get("refurbished", {})

    new_acc = {k: v for k, v in accessories.items() if k not in prev_acc}
    new_ref = {k: v for k, v in refurbished.items() if k not in prev_ref}

    print(f"   新品配件：{len(new_acc)} 項　|　新整修品：{len(new_ref)} 項")

    # 更新週記錄
    if new_acc or new_ref:
        update_weekly_log({**new_acc, **new_ref})

    # 發 Discord 通知
    send_new_items(new_acc, new_ref, len(accessories), len(refurbished))

    # 儲存快照
    save_json(SNAPSHOT_FILE, {
        "accessories": accessories,
        "refurbished": refurbished,
    })


if __name__ == "__main__":
    main()
