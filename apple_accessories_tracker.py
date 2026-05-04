#!/usr/bin/env python3
"""
Apple 台灣配件頁面 新品追蹤器
推播方式：Discord Webhook
執行環境：GitHub Actions（或本機）
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── 設定區 ───────────────────────────────────────────────────────
TARGET_URL = "https://www.apple.com/tw/shop/buy-accessories"

# Discord Webhook URL
# 本機執行時可直接填入；GitHub Actions 請設定在 Secrets（變數名稱：DISCORD_WEBHOOK_URL）
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "your_discord_webhook_url_here")

# 快照檔路徑（GitHub Actions 會用 cache 保存）
DATA_FILE = Path("snapshot.json")
# ──────────────────────────────────────────────────────────────────


def fetch_accessories(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9",
    }

    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    items = {}
    for card in soup.select("[class*='productitem'], [class*='product-item'], [class*='rf-product']"):
        name_tag  = card.select_one("[class*='title'], h3, h2")
        price_tag = card.select_one("[class*='price']")
        link_tag  = card.select_one("a[href]")

        if not name_tag:
            continue

        name  = name_tag.get_text(strip=True)
        price = price_tag.get_text(strip=True) if price_tag else "N/A"
        link  = "https://www.apple.com" + link_tag["href"] if link_tag else ""

        if name:
            items[name] = {"price": price, "link": link}

    return items


def load_snapshot() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_discord(new_items: dict):
    now = datetime.now().strftime("%Y/%m/%d %H:%M")

    # 組 Discord Embed 訊息
    fields = []
    for name, info in list(new_items.items())[:20]:  # Discord 最多 25 個 fields
        price = info.get("price", "N/A")
        link  = info.get("link", "")
        value = f"{price}"
        if link:
            value += f"\n[商品連結]({link})"
        fields.append({"name": name, "value": value, "inline": True})

    payload = {
        "embeds": [{
            "title": "🍎 Apple 台灣配件 — 新上架通知",
            "description": f"偵測到 **{len(new_items)}** 項新商品　|　{now}",
            "color": 0x000000,  # 黑色（Apple 風格）
            "fields": fields,
            "footer": {
                "text": "Apple 配件追蹤器"
            },
            "url": TARGET_URL,
        }]
    }

    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)

    if resp.status_code in (200, 204):
        print("✅ Discord 推播成功")
    else:
        print(f"⚠️  Discord 推播失敗：{resp.status_code} {resp.text}")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 開始檢查 Apple 配件頁面...")

    try:
        current = fetch_accessories(TARGET_URL)
    except Exception as e:
        print(f"❌ 抓取失敗：{e}")
        sys.exit(1)

    print(f"   目前偵測到 {len(current)} 項商品")

    previous  = load_snapshot()
    new_items = {k: v for k, v in current.items() if k not in previous}

    if new_items:
        print(f"🆕 發現 {len(new_items)} 項新上架：")
        for name in new_items:
            print(f"   • {name}")
        send_discord(new_items)
    else:
        print("   沒有新商品，下次再見！")

    save_snapshot(current)


if __name__ == "__main__":
    main()
