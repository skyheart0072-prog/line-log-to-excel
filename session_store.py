"""
session_store.py
เก็บสถานะ "การสนทนาค้าง" ของแต่ละ user (ตอนข้อมูลยังไม่ครบ รอผู้ใช้พิมพ์เพิ่ม)

เวอร์ชันนี้เก็บใน memory (dict) เหมาะกับ prototype / ผู้ใช้ไม่เยอะ
ถ้าจะใช้งานจริงระยะยาว ควรเปลี่ยนไปใช้ Redis เพราะ:
  - ถ้า server restart ข้อมูล session ใน memory จะหายทันที
  - ถ้ามี server มากกว่า 1 instance จะเก็บ state ไม่ตรงกัน
"""

from typing import Optional

_sessions: dict[str, dict] = {}


def get_session(user_id: str) -> Optional[dict]:
    return _sessions.get(user_id)


def set_session(user_id: str, data: dict) -> None:
    _sessions[user_id] = data


def clear_session(user_id: str) -> None:
    _sessions.pop(user_id, None)


# ---------------------------------------------------------------------------
# ตัวอย่างการสลับไปใช้ Redis ในอนาคต (แก้แค่ไฟล์นี้ไฟล์เดียว ไม่ต้องแก้ main.py)
#
# import redis, json
# r = redis.Redis(host=..., port=6379, decode_responses=True)
#
# def get_session(user_id):
#     raw = r.get(f"session:{user_id}")
#     return json.loads(raw) if raw else None
#
# def set_session(user_id, data):
#     r.setex(f"session:{user_id}", 900, json.dumps(data))  # หมดอายุใน 15 นาที
#
# def clear_session(user_id):
#     r.delete(f"session:{user_id}")
# ---------------------------------------------------------------------------
