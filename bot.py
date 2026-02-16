import os
import base64
import json
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import gspread
from google.oauth2.service_account import Credentials
# Добавляем планировщик
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

logging.basicConfig(level=logging.INFO)

# --- ПЕРЕМЕННЫЕ ---
TOKEN = os.getenv("BOT_TOKEN")
SHEET_NAME = os.getenv("SHEET_NAME")
GOOGLE_CAL = os.getenv("GOOGLE_CAL_URL")
APPLE_CAL = os.getenv("APPLE_CAL_URL")
BELGRADE_TZ = timezone('Europe/Belgrade')

def get_gspread_client():
    try:
        encoded_json = os.getenv("SERVICE_ACCOUNT_B64")
        decoded_json = json.loads(base64.b64decode(encoded_json.strip()))
        creds = Credentials.from_service_account_info(
            decoded_json, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        logging.error(f"Gspread error: {e}")
        return None

class Registration(StatesGroup):
    full_name = State()
    email = State()
    direction = State()
    custom_direction = State()
    company = State()
    experience = State()
    job_offers = State()
    known_g5 = State()

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=BELGRADE_TZ)

# --- РЕГИСТРАЦИЯ (те же 7 шагов) ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Здравствуйте! 👋\nВы регистрируетесь на митап от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве».\n\n"
        "(1/7) Введите ваши имя и фамилию:"
    )
    await state.set_state(Registration.full_name)

# ... (все промежуточные шаги из предыдущего кода остаются такими же) ...

@dp.message(Registration.known_g5)
async def finish_reg(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    full_name = user_data.get('full_name')
    
    try:
        client = get_gspread_client()
        if client:
            sheet = client.open(SHEET_NAME).get_worksheet(0)
            # Добавляем ID пользователя в 8-й столбец для рассылки
            sheet.append_row([
                full_name, user_data.get('email'), user_data.get('direction'), 
                user_data.get('company'), user_data.get('experience'), 
                user_data.get('job_offers'), message.text, message.from_user.id
            ])
    except Exception as e:
        logging.error(f"Table write error: {e}")

    cal_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Google Календарь", url=GOOGLE_CAL)],
        [InlineKeyboardButton(text="🍎 Apple Календарь", url=APPLE_CAL)]
    ])
    
    await message.answer(
        f"{full_name}, спасибо за регистрацию! 🎉\n"
        "Ждем вас на митапе от G5 Games:\n"
        "«Геймдев — от проблемы к результату»\n"
        "26 февраля в 18:00, Белград.\n\n"
        "Добавьте событие в календарь:", 
        reply_markup=cal_kb
    )
    await state.clear()

# --- ЛОГИКА УВЕДОМЛЕНИЙ ---

# 1. Рассылка за сутки (25 февраля в 15:00)
async def send_24h_reminder():
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).get_worksheet(0)
    users = sheet.get_all_values()[1:] # Пропускаем заголовок
    
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Я буду!"), KeyboardButton(text="❌ Изменились планы")]
    ], resize_keyboard=True, one_time_keyboard=True)

    for row in users:
        try:
            user_id = row[7] # ID в 8-й колонке
            await bot.send_message(
                user_id, 
                "🔔 Уже завтра митап от G5 Games: «Продукт и маркетинг в геймдеве»\n"
                "📅 26 февраля, 18:00\n📍 CDT Hub, Кнеза Милоша 12\n\n"
                "Подскажите, пожалуйста, сможете ли вы прийти?",
                reply_markup=kb
            )
        except: continue

# Обработка ответов на уведомление
@dp.message(F.text == "✅ Я буду!")
async def confirm_yes(message: types.Message):
    # Тут можно добавить логику отметки в таблице (например, в 9-ю колонку ставить "Да")
    await message.answer("Отлично! Мы отметили, что вы придете.\nДо встречи на митапе 👋", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.text == "❌ Изменились планы")
async def confirm_no(message: types.Message):
    # Тут ставим пометку "Нет" в таблицу
    await message.answer(
        "Понимаем, планы меняются 🙂\nСпасибо, что предупредили!\n"
        "Следите за анонсами будущих митапов в @g5careers.",
        reply_markup=types.ReplyKeyboardRemove()
    )

# 2. Рассылка за 3 часа (26 февраля в 15:00)
async def send_3h_reminder():
    # Логика: берем только тех, кто ответил "Я буду!" или всех (как решите)
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).get_worksheet(0)
    users = sheet.get_all_values()[1:]
    
    for row in users:
        try:
            user_id = row[7]
            await bot.send_message(user_id, "🚀 Мы начинаем сегодня в 18:00 — продуктовый митап от G5 Games\nДо скорой встречи в CDT Hub!")
        except: continue

# Настройка расписания
scheduler.add_job(send_24h_reminder, 'cron', month=2, day=25, hour=15, minute=0)
scheduler.add_job(send_3h_reminder, 'cron', month=2, day=26, hour=15, minute=0)

async def handle_hc(request): return web.Response(text="OK")
async def main():
    app = web.Application(); app.router.add_get("/", handle_hc)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    asyncio.create_task(site.start())
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())