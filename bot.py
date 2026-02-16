import os
import base64
import json
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import gspread
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

logging.basicConfig(level=logging.INFO)

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
        logging.error(f"Gspread Error: {e}")
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

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! 👋\nВы регистрируетесь на митап от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве».\n\n"
        "(1/7) Введите ваши имя и фамилию:"
    )
    await state.set_state(Registration.full_name)

@dp.message(Registration.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("(2/7) Введите ваш e-mail:")
    await state.set_state(Registration.email)

@dp.message(Registration.email)
async def process_email(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("Пожалуйста, введите корректный e-mail (с символом @):")
        return
    await state.update_data(email=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 Game Design"), KeyboardButton(text="📊 Product / Analytics")],
        [KeyboardButton(text="🎨 Art / Design"), KeyboardButton(text="💻 Development")],
        [KeyboardButton(text="📢 Marketing"), KeyboardButton(text="🧪 QA")],
        [KeyboardButton(text="🧠 Management / Lead"), KeyboardButton(text="📚 HR / Recruitment")],
        [KeyboardButton(text="✏️ Другое")]
    ], resize_keyboard=True)
    await message.answer("(3/7) В каком направлении вы сейчас работаете?", reply_markup=kb)
    await state.set_state(Registration.direction)

@dp.message(Registration.direction)
async def process_direction(message: types.Message, state: FSMContext):
    if message.text == "✏️ Другое":
        await message.answer("Пожалуйста, укажите ваше направление вручную:")
        await state.set_state(Registration.custom_direction)
    else:
        await state.update_data(direction=message.text)
        await ask_company(message, state)

@dp.message(Registration.custom_direction)
async def process_custom_direction(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await ask_company(message, state)

async def ask_company(message: types.Message, state: FSMContext):
    await message.answer("(4/7) В какой компании вы работаете?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Registration.company)

@dp.message(Registration.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="нет опыта"), KeyboardButton(text="менее 1 года")],
        [KeyboardButton(text="1-3 года"), KeyboardButton(text="3-6 лет")],
        [KeyboardButton(text="более 6 лет")]
    ], resize_keyboard=True)
    await message.answer("(5/7) Ваш опыт работы в геймдеве:", reply_markup=kb)
    await state.set_state(Registration.experience)

@dp.message(Registration.experience)
async def process_exp(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("(6/7) Вы рассматриваете новые рабочие предложения?", reply_markup=kb)
    await state.set_state(Registration.job_offers)

@dp.message(Registration.job_offers)
async def process_offers(message: types.Message, state: FSMContext):
    await state.update_data(job_offers=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("(7/7) Знали ли вы про компанию G5 Games ранее?", reply_markup=kb)
    await state.set_state(Registration.known_g5)

@dp.message(Registration.known_g5)
async def finish_reg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
    
    try:
        client = get_gspread_client()
        if client:
            sheet = client.open(SHEET_NAME).get_worksheet(0)
            # ПОРЯДОК: A:ID, B:Username, C:Name, D:Email, E:Pos, F:Comp, G:Exp, H:Job, I:KnowG5, J:Wait
            sheet.append_row([
                str(user_id), username, data.get('full_name'), data.get('email'),
                data.get('direction'), data.get('company'), data.get('experience'),
                data.get('job_offers'), message.text, "Wait"
            ])
    except Exception as e:
        logging.error(f"Write error: {e}")

    cal_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Google Календарь", url=GOOGLE_CAL)],
        [InlineKeyboardButton(text="🍎 Apple Календарь", url=APPLE_CAL)]
    ])
    
    await message.answer(
        f"{data.get('full_name')}, спасибо за регистрацию! 🎉\n"
        "Ждем вас на митапе от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве»\n"
        "26 февраля в 18:00, Кнеза Милоша 12 (CDT Hub).\n\n"
        "Добавьте событие в календарь:", 
        reply_markup=cal_kb
    )
    await state.clear()

# --- REMINDERS ---
async def update_status(user_id, status):
    try:
        client = get_gspread_client()
        sheet = client.open(SHEET_NAME).get_worksheet(0)
        cell = sheet.find(str(user_id))
        sheet.update_cell(cell.row, 10, status) # Колонка J
    except: pass

@dp.message(F.text == "✅ Я буду!")
async def confirm_yes(message: types.Message):
    await update_status(message.from_user.id, "Coming")
    await message.answer("Отлично! Мы отметили, что вы придете.\nДо встречи на митапе 👋", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.text == "❌ Изменились планы")
async def confirm_no(message: types.Message):
    await update_status(message.from_user.id, "Declined")
    await message.answer("Понимаем, планы меняются 🙂\nСпасибо, что предупредили!\nСледите за анонсами в @g5careers.", reply_markup=types.ReplyKeyboardRemove())

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