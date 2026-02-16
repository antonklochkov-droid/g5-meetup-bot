import os
import json
import base64
import asyncio
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from dotenv import load_dotenv

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -----------------
# CONFIG
# -----------------
load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
SHEET_NAME = (os.getenv("SHEET_NAME") or "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Railway Variables.")
if not SHEET_NAME:
    raise RuntimeError("SHEET_NAME is not set in Railway Variables.")

DEFAULT_GOOGLE_CAL_URL = (
    "https://calendar.google.com/calendar/render?action=TEMPLATE"
    "&text=G5%20Games%20%D0%BC%D0%B8%D1%82%D0%B0%D0%BF%3A%20%D0%9F%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%20%D0%B8%20%D0%BC%D0%B0%D1%80%D0%BA%D0%B5%D1%82%D0%B8%D0%BD%D0%B3%20%D0%B2%20%D0%B3%D0%B5%D0%B9%D0%BC%D0%B4%D0%B5%D0%B2%D0%B5"
    "&dates=20260226T180000/20260226T210000"
    "&ctz=Europe/Belgrade"
)
GOOGLE_CAL_URL = (os.getenv("GOOGLE_CAL_URL") or DEFAULT_GOOGLE_CAL_URL).strip()
APPLE_CAL_URL = (os.getenv("APPLE_CAL_URL") or "").strip()

serbia_tz = pytz.timezone("Europe/Belgrade")
REMINDER1_DT = serbia_tz.localize(datetime(2026, 2, 25, 15, 0, 0))
REMINDER2_DT = serbia_tz.localize(datetime(2026, 2, 26, 15, 0, 0))

MAPS_URL = "https://www.google.com/maps/search/?api=1&query=CDT%20Hub%2C%20Kneza%20Milo%C5%A1a%2012%2C%20Belgrade"
CONFIRMED_COL = 10  # J

# -----------------
# GOOGLE SHEETS AUTH
# -----------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

def build_gspread_client():
    sa_json = (os.getenv("SERVICE_ACCOUNT_JSON") or "").strip()
    sa_b64 = (os.getenv("SERVICE_ACCOUNT_B64") or "").strip()

    if sa_json:
        try:
            info = json.loads(sa_json)
            return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(info, scope))
        except Exception as e:
            print(f"DEBUG: JSON error: {e}")

    if sa_b64:
        try:
            decoded = base64.b64decode(sa_b64).decode("utf-8")
            info = json.loads(decoded)
            return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(info, scope))
        except Exception as e:
            print(f"DEBUG: Base64 error: {e}")

    if os.path.exists("service_account.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        return gspread.authorize(creds)

    raise RuntimeError("Google credentials not found! Check SERVICE_ACCOUNT_B64 in Railway.")

client = build_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# -----------------
# BOT LOGIC
# -----------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=serbia_tz)

class Registration(StatesGroup):
    full_name = State()
    email = State()
    position = State()
    custom_position = State()
    company = State()
    experience = State()
    job_search = State()
    know_g5 = State()

def find_user_row(user_id: int) -> int | None:
    col = sheet.col_values(1)
    for idx, val in enumerate(col[1:], start=2):
        if str(val) == str(user_id): return idx
    return None

def update_confirmed(user_id: int, value: str) -> bool:
    row = find_user_row(user_id)
    if row is None: return False
    sheet.update_cell(row, CONFIRMED_COL, value)
    return True

def build_confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Я буду!", callback_data="confirm_yes"))
    kb.row(types.InlineKeyboardButton(text="❌ Изменились планы", callback_data="confirm_no"))
    return kb.as_markup()

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await message.answer("Здравствуйте! 👋\n(1/7) Введите ваши имя и фамилию:")
    await state.set_state(Registration.full_name)

@dp.message(Registration.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer("(2/7) Введите ваш e-mail:")
    await state.set_state(Registration.email)

@dp.message(Registration.email)
async def process_email(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("Введите корректный e-mail:")
        return
    await state.update_data(email=message.text.strip())
    kb = ReplyKeyboardBuilder()
    for d in ["🎮 Game Design", "📊 Product", "🎨 Art", "💻 Dev", "📢 Marketing", "✏️ Другое"]:
        kb.add(types.KeyboardButton(text=d))
    await message.answer("(3/7) Направление работы:", reply_markup=kb.adjust(2).as_markup(resize_keyboard=True))
    await state.set_state(Registration.position)

@dp.message(Registration.position)
async def process_position(message: types.Message, state: FSMContext):
    if message.text == "✏️ Другое":
        await message.answer("Укажите вручную:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Registration.custom_position)
        return
    await state.update_data(position=message.text)
    await message.answer("(4/7) Компания:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.company)

@dp.message(Registration.custom_position)
async def process_custom_position(message: types.Message, state: FSMContext):
    await state.update_data(position=message.text)
    await message.answer("(4/7) Компания:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.company)

@dp.message(Registration.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    kb = ReplyKeyboardBuilder()
    for i in ["нет опыта", "1-3 года", "более 3 лет"]:
        kb.add(types.KeyboardButton(text=i))
    await message.answer("(5/7) Опыт:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(Registration.experience)

@dp.message(Registration.experience)
async def process_experience(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    kb = ReplyKeyboardBuilder().add(types.KeyboardButton(text="Да"), types.KeyboardButton(text="Нет"))
    await message.answer("(6/7) Ищете работу?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(Registration.job_search)

@dp.message(Registration.job_search)
async def process_job_search(message: types.Message, state: FSMContext):
    await state.update_data(job_search=message.text)
    kb = ReplyKeyboardBuilder().add(types.KeyboardButton(text="Да"), types.KeyboardButton(text="Нет"))
    await message.answer("(7/7) Знали о G5?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(Registration.know_g5)

@dp.message(Registration.know_g5)
async def finish(message: types.Message, state: FSMContext):
    await state.update_data(know_g5=message.text)
    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    
    values = [user_id, username, data.get("full_name"), data.get("email"), data.get("position"), data.get("company"), data.get("experience"), data.get("job_search"), data.get("know_g5"), ""]
    
    row = find_user_row(user_id)
    if row: sheet.update(f"A{row}:J{row}", [values])
    else: sheet.append_row(values)

    await message.answer("🎉 Регистрация завершена! Ждем вас 26 февраля.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.callback_query(F.data.in_(["confirm_yes", "confirm_no"]))
async def confirm_attendance(callback: types.CallbackQuery):
    status = "yes" if callback.data == "confirm_yes" else "no"
    if update_confirmed(callback.from_user.id, status):
        msg = "Спасибо! Мы вас отметили."
    else:
        msg = "Сначала зарегистрируйтесь через /start"
    await callback.message.answer(msg)
    await callback.answer()

# -----------------
# RAILWAY HEALTHCHECK & MAIN
# -----------------
async def handle_hc(request):
    return web.Response(text="Bot is Alive")

async def main():
    # Запуск микро-сервера для Railway
    app = web.Application()
    app.router.add_get("/", handle_hc)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    asyncio.create_task(site.start())
    print(f"Healthcheck server started on port {port}")

    await bot.delete_webhook(drop_pending_updates=True)
    scheduler.start()
    print("Bot is starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())