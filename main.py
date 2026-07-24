"""
main.py
LINE Webhook -> ตรวจสอบสิทธิ์ -> กรอง keyword -> Gemini AI -> เขียน Excel -> แจ้งเตือนกลับ

รันตอน dev:
    uvicorn main:app --reload --port 8000

รันตอน production (Render จะเรียกแบบนี้):
    uvicorn main:app --host 0.0.0.0 --port 10000
"""

import os
import hmac
import hashlib
import base64
import logging
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from dotenv import load_dotenv

from session_store import get_session, set_session, clear_session
from master_data import load_master_data, is_user_allowed
from gemini_service import analyze_message
from gsheet_writer import append_rows
from line_client import reply_message, push_message, get_display_name

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("line-log-bot")

app = FastAPI()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
ALLOWED_USER_IDS = set(
    uid.strip() for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()
)

# โหลด master data (สาขา / ทีมงาน) ครั้งเดียวตอน server เริ่ม
MASTER_DATA = load_master_data()


def verify_signature(body: bytes, signature: str) -> bool:
    """ตรวจสอบว่า request มาจาก LINE จริง ไม่ใช่ของปลอม"""
    if not LINE_CHANNEL_SECRET:
        # ถ้ายังไม่ตั้งค่า secret (เช่นตอน dev) ให้ผ่านไปก่อนแต่ log เตือนไว้
        logger.warning("LINE_CHANNEL_SECRET ไม่ถูกตั้งค่า - ข้ามการ verify (ไม่ควรใช้ใน production)")
        return True
    hash_ = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(hash_).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(None),
):
    body = await request.body()

    if not verify_signature(body, x_line_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    events = payload.get("events", [])

    # ตอบ LINE กลับทันที (200) แล้วค่อยประมวลผลเบื้องหลัง
    # กัน LINE ส่ง event ซ้ำเพราะคิดว่า server ไม่ตอบ
    for event in events:
        background_tasks.add_task(handle_event, event)

    return {"status": "ok"}


def handle_event(event: dict):
    try:
        if event.get("type") != "message":
            return
        message = event.get("message", {})
        if message.get("type") != "text":
            return

        user_id = event.get("source", {}).get("userId")
        reply_token = event.get("replyToken")
        text = message.get("text", "").strip()

        if not user_id:
            return

        # 1) ตรวจสอบสิทธิ์ผู้ใช้งาน
        if not is_user_allowed(user_id, ALLOWED_USER_IDS):
            reply_message(reply_token, "คุณไม่มีสิทธิ์ใช้งานระบบนี้")
            return

        # 2) กรองข้อความทั่วไปที่ไม่เกี่ยวข้องด้วย keyword ก่อนยิง AI (ประหยัดค่า API)
        if not looks_like_log(text):
            # ปล่อยผ่าน ไม่ตอบ ไม่บันทึก
            return

        # 3) เช็คว่ามี session ค้างอยู่ไหม (กำลังรอข้อมูลเพิ่มจากคำถามก่อนหน้า)
        session = get_session(user_id)
        if session:
            # เอาข้อความใหม่ไปต่อกับข้อความเดิม แล้วส่งให้ AI วิเคราะห์ใหม่อีกครั้ง
            combined_text = session["original_text"] + "\n" + text
        else:
            combined_text = text

        display_name = get_display_name(user_id) or "ไม่ทราบชื่อ"

        # 4) ส่งให้ Gemini AI วิเคราะห์ (อาจได้หลายรายการถ้า 1 ข้อความมีหลายเหตุการณ์)
        result = analyze_message(combined_text, MASTER_DATA)

        if not result.get("complete"):
            missing = result.get("missing_fields", [])
            set_session(user_id, {"original_text": combined_text})
            question = result.get(
                "follow_up_question",
                f"ขอข้อมูลเพิ่มเติม: {', '.join(missing)}",
            )
            reply_message(reply_token, question)
            return

        # ข้อมูลครบแล้ว เคลียร์ session ค้าง
        clear_session(user_id)

        rows = result.get("items", [])
        if not rows:
            reply_message(reply_token, "ไม่พบข้อมูลที่เข้าใจได้ ลองพิมพ์อีกครั้ง")
            return

        # 5) เขียนลง Excel (retry ในตัว)
        write_ok = append_rows(rows, display_name)

        if write_ok:
            summary = "\n".join(
                f"- {r.get('branch','')} : {r.get('incident','')}" for r in rows
            )
            reply_message(
                reply_token,
                f"บันทึกเรียบร้อย {len(rows)} รายการ\n{summary}",
            )
        else:
            reply_message(
                reply_token,
                "บันทึกลง Excel ไม่สำเร็จ ระบบจะลองใหม่อัตโนมัติ กรุณาตรวจสอบภายหลัง",
            )

    except Exception:
        logger.exception("เกิดข้อผิดพลาดระหว่างประมวลผล event")


def looks_like_log(text: str) -> bool:
    """กรองคร่าวๆ ว่าข้อความนี้น่าจะเป็น log แจ้งปัญหาหรือไม่ (คัดข้อความทั่วไปออกก่อนยิง AI)"""
    if len(text) < 5:
        return False
    ignore_words = ["สวัสดี", "ขอบคุณ", "ok", "555", "ครับ", "ค่ะ"]
    stripped = text.strip().lower()
    if stripped in [w.lower() for w in ignore_words]:
        return False
    return True


@app.get("/")
def health_check():
    return {"status": "running"}
