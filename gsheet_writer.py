"""
gsheet_writer.py
เขียนข้อมูลต่อท้ายชีต "Cleaned_Data" ใน Google Sheets แทนไฟล์ Excel บน server
(ไฟล์ Excel บน Render จะหายทุกครั้งที่ deploy ใหม่ เพราะ filesystem เป็นแบบชั่วคราว
 Google Sheets แก้ปัญหานี้เพราะข้อมูลอยู่บน Google เอง ไม่ผูกกับ container)

Schema เหมือนเดิมทุกอย่าง:
No | Date | Time | Incident | Branch / User | Project | Action | Status | Reference ID(F1) | IT Support

Status และ Reference ID(F1) เว้นว่างเสมอ (ให้คนกรอกเอง)
"""

import os
import json
import time
import logging
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger("line-log-bot")

SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
WORKSHEET_NAME = "Cleaned_Data"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

_client = None
_worksheet = None


def _get_client():
    """สร้าง gspread client จาก Service Account JSON ที่เก็บใน environment variable"""
    global _client
    if _client is not None:
        return _client

    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw_json:
        raise RuntimeError(
            "ไม่พบ GOOGLE_SERVICE_ACCOUNT_JSON ใน environment variable "
            "กรุณาตั้งค่าตามขั้นตอนใน README ก่อนใช้งาน"
        )

    info = json.loads(raw_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    _client = gspread.authorize(creds)
    return _client


def _get_worksheet():
    """เปิด worksheet Cleaned_Data (cache ไว้ ไม่ต้องเปิดใหม่ทุกครั้ง)"""
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    if not SHEET_ID:
        raise RuntimeError(
            "ไม่พบ GOOGLE_SHEET_ID ใน environment variable "
            "กรุณาตั้งค่าตามขั้นตอนใน README ก่อนใช้งาน"
        )

    client = _get_client()
    sh = client.open_by_key(SHEET_ID)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=10)
        ws.append_row([
            "No", "Date", "Time", "Incident", "Branch / User",
            "Project", "Action", "Status", "Reference ID(F1)", "IT Support",
        ])

    _worksheet = ws
    return _worksheet


def _next_no(ws) -> int:
    """หาเลขลำดับถัดไปจากคอลัมน์ No (คอลัมน์ A)"""
    col_values = ws.col_values(1)
    numeric_values = []
    for v in col_values[1:]:
        try:
            numeric_values.append(int(v))
        except (ValueError, TypeError):
            continue
    return (max(numeric_values) + 1) if numeric_values else 1


def append_rows(items: list[dict], display_name: str) -> bool:
    """
    เขียนหลายแถวลง Google Sheet ในครั้งเดียว
    คืนค่า True/False ว่าสำเร็จหรือไม่ - retry อัตโนมัติถ้าเจอ error ชั่วคราว
    """
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ws = _get_worksheet()
            no = _next_no(ws)

            rows_to_add = []
            for item in items:
                rows_to_add.append([
                    no,
                    date_str,
                    time_str,
                    item.get("incident", ""),
                    item.get("branch", "") or display_name,
                    item.get("project", ""),
                    item.get("action", ""),
                    "",
                    "",
                    item.get("it_support", ""),
                ])
                no += 1

            ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")

            logger.info(f"บันทึก {len(items)} แถวลง Google Sheet สำเร็จ (attempt {attempt})")
            return True

        except gspread.exceptions.APIError as e:
            logger.warning(f"Google Sheets API error (attempt {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(RETRY_DELAY_SECONDS * attempt)
        except Exception:
            logger.exception(f"เขียน Google Sheet ไม่สำเร็จ (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY_SECONDS)

    logger.error("เขียน Google Sheet ไม่สำเร็จหลังจาก retry ครบแล้ว")
    return False