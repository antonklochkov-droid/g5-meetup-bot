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

# Логирование для отладки
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
SHEET_NAME = os.getenv("SHEET_NAME")
GOOGLE_CAL = os.getenv("GOOGLE_CAL_URL")
APPLE_CAL = os.getenv("APPLE_CAL_URL")

def get_gspread_client():
    try:
        encoded_json = os.getenv("SERVICE_ACCOUNT_B64")
        # Удаляем возможные пробелы/переносы строк из base64
        decoded_json = json.loads(base64.b64decode(encoded_json.strip()))
        creds = Credentials.from_service_account_info(
            decoded_json, 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        logging.error(f"CRITICAL: Base64 decode error: {e}")
        return None

class RegSteps(StatesGroup):
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

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Здравствуйте! 👋\nВы регистрируетесь на митап от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве».\n\n"
        "(1/7) Введите ваши имя и фамилию:"
    )
    await state.set_state(RegSteps.full_name)

@dp.message(RegSteps.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("(2/7) Введите ваш e-mail:")
    await state.set_state(RegSteps.email)

@dp.message(RegSteps.email)
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
    await state.set_state(RegSteps.direction)

@dp.message(RegSteps.direction)
async def process_direction(message: types.Message, state: FSMContext):
    if message.text == "✏️ Другое":
        await message.answer("Пожалуйста, укажите ваше направление вручную:")
        await state.set_state(RegSteps.custom_direction)
    else:
        await state.update_data(direction=message.text)
        await ask_company(message, state)

@dp.message(RegSteps.custom_direction)
async def process_custom_direction(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await ask_company(message, state)

async def ask_company(message: types.Message, state: FSMContext):
    await message.answer("(4/7) В какой компании вы работаете?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(RegSteps.company)

@dp.message(RegSteps.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="нет опыта"), KeyboardButton(text="менее 1 года")],
        [KeyboardButton(text="1-3 года"), KeyboardButton(text="3-6 лет")],
        [KeyboardButton(text="более 6 лет")]
    ], resize_keyboard=True)
    await message.answer("(5/7) Ваш опыт работы в геймдеве:", reply_markup=kb)
    await state.set_state(RegSteps.experience)

@dp.message(RegSteps.experience)
async def process_exp(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("(6/7) Вы рассматриваете новые рабочие предложения?", reply_markup=kb)
    await state.set_state(RegSteps.job_offers)

@dp.message(RegSteps.job_offers)
async def process_offers(message: types.Message, state: FSMContext):
    await state.update_data(job_offers=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("(7/7) Знали ли вы про компанию G5 Games ранее?", reply_markup=kb)
    await state.set_state(RegSteps.known_g5)

@dp.message(RegSteps.known_g5)
async def finish_reg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['known_g5'] = message.text
    
    try:
        client = get_gspread_client()
        if client:
            sheet = client.open(SHEET_NAME).get_worksheet(0)
            sheet.append_row([
                data['full_name'], data['email'], data['direction'], 
                data['company'], data['experience'], data['job_offers'], data['known_g5']
            ])
            logging.info("SUCCESS: Data added to sheet")
        else:
            logging.error("ERROR: Gspread client is None")
    except Exception as e:
        logging.error(f"TABLE ERROR: {e}")

    cal_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Google Календарь", url=GOOGLE_CAL)],
        [InlineKeyboardButton(text="🍎 Apple Календарь", url=APPLE_CAL)]
    ])
    
    await message.answer(
        f"{data['full_name']}, спасибо за регистрацию! 🎉\n"
        "Ждем вас на митапе от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве»\n"
        "26 февраля в 18:00, Белград.\n\n"
        "Добавьте событие в календарь:", 
        reply_markup=cal_kb
    )
    await state.clear()

async def handle_hc(request): return web.Response(text="OK")
async def main():
    app = web.Application(); app.router.add_get("/", handle_hc)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    asyncio.create_task(site.start())
    logging.info("Bot is starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())