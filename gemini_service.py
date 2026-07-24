"""
gemini_service.py
ส่งข้อความ log ให้ Gemini ตีความ พร้อมจับคู่กับ master data
บังคับให้ Gemini ตอบเป็น JSON เท่านั้น เพื่อ parse ต่อได้ง่ายและปลอดภัย
"""

import os
import json
import logging
import google.generativeai as genai

logger = logging.getLogger("line-log-bot")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

SYSTEM_INSTRUCTION = """\
คุณคือระบบตีความข้อความแจ้งปัญหา (log) จากพนักงานหน้างาน ที่พิมพ์ผ่าน LINE
หน้าที่ของคุณ:
1. อ่านข้อความ อาจมี "หลายเหตุการณ์ปนกันในข้อความเดียว" (เช่น list เป็นข้อๆ) ให้แยกเป็นหลายรายการ
2. จับคู่ชื่อสาขา/ประเภทงานกับ master data ที่ให้มา ถ้าจับคู่ไม่ได้ให้เดาจากบริบทแต่ทำเครื่องหมายไว้
3. ระบุทีม IT Support ที่ควรดูแล โดยจับคู่จาก keyword ในตาราง Master_Issue
4. ตรวจสอบว่าข้อมูลครบหรือไม่ (อย่างน้อยต้องมี: อาการ/ปัญหา และ สาขาหรือผู้แจ้ง)
   ถ้าไม่ครบ ให้ตั้ง complete=false และใส่คำถามที่ควรถามกลับผู้ใช้ใน follow_up_question

ตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอกเหนือจาก JSON ห้ามใช้ markdown code fence
รูปแบบ JSON ที่ต้องตอบ:
{
  "complete": true หรือ false,
  "missing_fields": ["..."],
  "follow_up_question": "คำถามที่จะถามผู้ใช้ถ้าข้อมูลไม่ครบ (ใส่เฉพาะตอน complete=false)",
  "items": [
    {
      "incident": "สรุปอาการ/ปัญหา แบบสั้น กระชับ",
      "branch": "ชื่อสาขาหรือชื่อผู้แจ้ง",
      "project": "ATM หรือ Office หรือ Loan หรือประเภทอื่นตาม master data",
      "action": "สิ่งที่ทำหรือวิธีแก้ ถ้าไม่มีในข้อความให้ใส่ค่าว่าง",
      "it_support": "ชื่อทีมที่ควรดูแล จับคู่จาก master data"
    }
  ]
}
"""


def _build_master_context(master_data: dict) -> str:
    branches = master_data.get("branches", [])
    issue_teams = master_data.get("issue_teams", [])

    branch_lines = "\n".join(
        f"- {b['code']} : {b['name']} (ประเภทงาน: {b.get('project','')})" for b in branches
    ) or "(ไม่มีข้อมูล master สาขา)"

    issue_lines = "\n".join(
        f"- คำที่เกี่ยวข้อง '{t['keyword']}' -> ทีม {t['it_support']}" for t in issue_teams
    ) or "(ไม่มีข้อมูล master ทีมงาน)"

    return f"ตาราง Master_Branch:\n{branch_lines}\n\nตาราง Master_Issue:\n{issue_lines}"


def analyze_message(text: str, master_data: dict) -> dict:
    """
    ส่งข้อความให้ Gemini วิเคราะห์ คืนค่าเป็น dict ตาม schema ด้านบน
    ถ้า parse ไม่ได้หรือเกิด error จะคืน complete=False พร้อมคำถามให้ผู้ใช้พิมพ์ใหม่
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY ไม่ถูกตั้งค่า")
        return {
            "complete": False,
            "follow_up_question": "ระบบ AI ยังไม่พร้อมใช้งาน กรุณาติดต่อผู้ดูแลระบบ",
            "items": [],
        }

    master_context = _build_master_context(master_data)
    prompt = f"{master_context}\n\nข้อความจากผู้ใช้:\n\"\"\"\n{text}\n\"\"\""

    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        raw = response.text.strip()
        data = json.loads(raw)

        # validate โครงสร้างขั้นต่ำ กัน AI ตอบมั่ว
        if "complete" not in data or "items" not in data:
            raise ValueError("โครงสร้าง JSON ที่ Gemini ตอบกลับมาไม่ครบตาม schema")

        return data

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Gemini ตอบกลับ format ผิด: {e}")
        return {
            "complete": False,
            "follow_up_question": "ระบบไม่เข้าใจข้อความ กรุณาพิมพ์รายละเอียดปัญหาอีกครั้ง",
            "items": [],
        }
    except Exception as e:
        logger.error(f"เรียก Gemini API ไม่สำเร็จ: {e}")
        return {
            "complete": False,
            "follow_up_question": "ระบบขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้งในภายหลัง",
            "items": [],
        }
