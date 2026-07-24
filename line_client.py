"""
line_client.py
เรียก LINE Messaging API แบบ HTTP ตรงๆ (ไม่ผูกกับ SDK version ใดเป็นพิเศษ)
"""

import os
import logging
import requests 
from typing import Optional

logger = logging.getLogger("line-log-bot")

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

BASE_URL = "https://api.line.me/v2/bot"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
}


def reply_message(reply_token: str, text: str) -> None:
    if not reply_token:
        return
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    try:
        resp = requests.post(f"{BASE_URL}/message/reply", headers=HEADERS, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"reply_message ล้มเหลว: {resp.status_code} {resp.text}")
    except requests.RequestException:
        logger.exception("เรียก LINE reply_message ไม่สำเร็จ")


def push_message(user_id: str, text: str) -> None:
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }
    try:
        resp = requests.post(f"{BASE_URL}/message/push", headers=HEADERS, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"push_message ล้มเหลว: {resp.status_code} {resp.text}")
    except requests.RequestException:
        logger.exception("เรียก LINE push_message ไม่สำเร็จ")


def get_display_name(user_id: str) -> Optional[str]:
    try:
        resp = requests.get(f"{BASE_URL}/profile/{user_id}", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("displayName")
    except requests.RequestException:
        logger.exception("เรียก LINE get_profile ไม่สำเร็จ")
    return None
