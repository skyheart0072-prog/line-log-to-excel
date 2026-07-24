# LINE Log to Excel (AI Logger)

บอท LINE ที่ให้พนักงานพิมพ์แจ้งปัญหา (log) แล้วให้ Gemini AI ช่วยตีความ จับคู่สาขา/ทีมงาน
และบันทึกลง Excel (ชีต `Cleaned_Data`) อัตโนมัติ รองรับ 1 ข้อความที่มีหลายเหตุการณ์ปนกัน
(จะแตกเป็นหลายแถวให้อัตโนมัติ)

## โครงสร้างโปรเจค
```
line-log-to-excel/
├── main.py            FastAPI app + webhook endpoint + orchestration
├── line_client.py      เรียก LINE Messaging API (reply / push / get profile)
├── gemini_service.py   เรียก Gemini AI ให้ตีความข้อความ
├── excel_writer.py     เขียนข้อมูลลง Cleaned_Data.xlsx (มี retry)
├── master_data.py      โหลด master data (สาขา / ทีมงาน) และตรวจสอบสิทธิ์ผู้ใช้
├── session_store.py    เก็บสถานะสนทนาค้าง (รอข้อมูลเพิ่ม)
├── data/
│   ├── Cleaned_Data.xlsx    ไฟล์ปลายทางที่ระบบจะเขียนข้อมูลลงไป
│   └── master_data.xlsx     ข้อมูลอ้างอิง (แก้ไข/เพิ่มสาขาและทีมงานได้ที่นี่)
├── requirements.txt
└── .env.example
```

---

## ขั้นตอนที่ 1 — สมัคร LINE Official Account + Messaging API

1. เข้า https://developers.line.biz/ แล้ว login ด้วยบัญชี LINE
2. สร้าง **Provider** ใหม่ (ตั้งชื่อบริษัท/ทีมก็ได้)
3. สร้าง **Channel** ประเภท **Messaging API**
4. ในหน้า Channel ไปที่แท็บ **Messaging API**:
   - เลื่อนลงไปคัดลอก **Channel access token** (ถ้ายังไม่มี ให้กด Issue)
   - กลับไปแท็บ **Basic settings** คัดลอก **Channel secret**
5. เก็บค่าทั้งสองไว้ก่อน จะใช้ในขั้นตอนที่ 4

## ขั้นตอนที่ 2 — เตรียม Gemini API Key

1. เข้า https://aistudio.google.com/
2. สร้าง API key ใหม่ แล้วคัดลอกเก็บไว้

## ขั้นตอนที่ 3 — ติดตั้งโปรเจคบนเครื่อง (ทดสอบก่อน deploy)

```bash
# 1) สร้าง virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2) ติดตั้ง dependencies
pip install -r requirements.txt

# 3) คัดลอกไฟล์ env แล้วใส่ค่าจริง
cp .env.example .env
```

เปิดไฟล์ `.env` แล้วใส่ค่า:
```
LINE_CHANNEL_ACCESS_TOKEN=ค่าที่คัดลอกจากขั้นตอนที่ 1
LINE_CHANNEL_SECRET=ค่าที่คัดลอกจากขั้นตอนที่ 1
ALLOWED_USER_IDS=U....(LINE user id ของคนที่อนุญาต คั่นด้วย comma)
GEMINI_API_KEY=ค่าที่คัดลอกจากขั้นตอนที่ 2
```

> **หา LINE User ID ของตัวเองยังไง?** วิธีง่ายที่สุดคือปิด `ALLOWED_USER_IDS` ไว้ก่อน (เว้นว่าง) แล้วดู log
> ตอนพิมพ์ทดสอบครั้งแรก ระบบจะ log user_id ที่ส่งเข้ามาให้เห็น ค่อยเอาไปใส่ทีหลัง

รันทดสอบในเครื่อง:
```bash
uvicorn main:app --reload --port 8000
```
ตอนนี้จะรันได้เฉพาะ localhost ยังเชื่อม LINE จริงไม่ได้ (เพราะ LINE ต้องการ HTTPS URL ที่เข้าถึงจากเน็ตได้)

## ขั้นตอนที่ 4 — Deploy ขึ้น Render (ฟรี ไม่ต้องใช้บัตร)

1. Push โปรเจคนี้ขึ้น GitHub repository (repo private ได้)
   - **สำคัญ:** อย่า push ไฟล์ `.env` ขึ้นไป ให้เพิ่ม `.env` ใน `.gitignore`
2. เข้า https://render.com สมัครด้วย GitHub
3. กด **New** → **Web Service** → เลือก repo นี้
4. ตั้งค่า:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port 10000`
5. ไปที่แท็บ **Environment** ใส่ตัวแปรทั้งหมดจาก `.env` (LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, ALLOWED_USER_IDS, GEMINI_API_KEY เป็นต้น)
6. กด **Deploy** รอจนสถานะเป็น **Live** จะได้ URL ประมาณ `https://line-log-to-excel.onrender.com`

> ข้อควรรู้: web service ฟรีของ Render จะ sleep หลังไม่มีคนเรียก 15 นาที และตื่นใหม่ใช้เวลา ~30-60 วินาที
> ถ้าไม่มีคนพิมพ์ log นานๆ ข้อความแรกอาจจะตอบช้าหน่อย เป็นเรื่องปกติของ free tier

## ขั้นตอนที่ 5 — ผูก Webhook URL กับ LINE

1. กลับไปที่ LINE Developers Console → แท็บ Messaging API
2. ใส่ **Webhook URL** เป็น `https://<your-app>.onrender.com/webhook`
3. กด **Verify** ให้ขึ้นสถานะสำเร็จ
4. เปิดสวิตช์ **Use webhook** เป็น ON
5. (แนะนำ) ปิด **Auto-reply messages** และ **Greeting messages** ในหน้า LINE Official Account Manager
   เพื่อไม่ให้ LINE ตอบข้อความอัตโนมัติซ้อนกับบอทของเรา

## ขั้นตอนที่ 6 — แก้ไข Master Data ให้ตรงกับหน้างานจริง

เปิดไฟล์ `data/master_data.xlsx`:
- ชีต **Master_Branch**: ใส่รหัสสาขา / ชื่อสาขา / ประเภทงาน (ATM, Office, Loan) ให้ครบทุกสาขาที่มีจริง
- ชีต **Master_Issue**: ใส่ keyword ที่มักเจอในปัญหา กับทีม IT Support ที่ควรดูแล เช่น "เหรียญติด" → Flook

ยิ่งใส่ครบ AI จะจับคู่ได้แม่นขึ้น ถ้าจับคู่ไม่ได้เลย AI จะเดาจากบริบทแทน

## ขั้นตอนที่ 7 — ทดสอบใช้งานจริง

ลองพิมพ์ในกลุ่ม LINE หรือแชทส่วนตัวกับบอท:
```
CJ0344 ตู้ ATM เหรียญติด รอตรวจสอบ
```
บอทควรตอบกลับว่าบันทึกสำเร็จ แล้วเช็คไฟล์ `data/Cleaned_Data.xlsx` ว่ามีแถวใหม่เพิ่มขึ้น

ทดสอบเคสข้อมูลไม่ครบ เช่นพิมพ์แค่ `เหรียญติด` (ไม่ระบุสาขา) — บอทควรถามกลับขอสาขาเพิ่ม

ทดสอบเคสหลายเหตุการณ์ในข้อความเดียว เช่น list เป็นข้อๆ หลายสาขา — ควรถูกแตกเป็นหลายแถวใน Excel

---

## ข้อจำกัดที่ควรรู้ (สำหรับใช้งานจริงระยะยาว)

- **session_store.py** เก็บ state ใน memory เท่านั้น ถ้า server restart (เช่น Render deploy ใหม่) session ที่ค้างอยู่จะหาย ผู้ใช้ต้องพิมพ์ log นั้นใหม่ตั้งแต่ต้น ถ้าต้องการแก้ไข ดูคอมเมนต์ตัวอย่างการสลับไปใช้ Redis ในไฟล์นั้น
- **Excel ไฟล์เดียว** เขียนพร้อมกันจากหลาย request ได้ไม่ดีเท่า database จริง ถ้าปริมาณ log เยอะมากในอนาคต ควรพิจารณาย้ายไป Google Sheets หรือฐานข้อมูลจริง
- **ALLOWED_USER_IDS** ต้องดูแลลิสต์เองตอนมีพนักงานเข้า-ออก ยังไม่มีหน้าจอจัดการสิทธิ์
