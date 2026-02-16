import os
import asyncio
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_NAME = os.getenv("SHEET_NAME")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")
if not SHEET_NAME:
    raise RuntimeError("SHEET_NAME is not set in .env")

# можно переопределить через .env, но есть дефолт
DEFAULT_GOOGLE_CAL_URL = (
    "https://calendar.google.com/calendar/render?action=TEMPLATE"
    "&text=G5%20Games%20%D0%BC%D0%B8%D1%82%D0%B0%D0%BF%3A%20%D0%9F%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%20%D0%B8%20%D0%BC%D0%B0%D1%80%D0%BA%D0%B5%D1%82%D0%B8%D0%BD%D0%B3%20%D0%B2%20%D0%B3%D0%B5%D0%B9%D0%BC%D0%B4%D0%B5%D0%B2%D0%B5"
    "&dates=20260226T180000/20260226T210000"
    "&ctz=Europe/Belgrade"
    "&details=%D0%9C%D0%B8%D1%82%D0%B0%D0%BF%20G5%20Games%20%D0%BE%20%D1%82%D0%BE%D0%BC%2C%20%D0%BA%D0%B0%D0%BA%20%D0%B2%20%D1%80%D0%B5%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D1%81%D1%82%D0%B8%20%D0%BF%D1%80%D0%B8%D0%BD%D0%B8%D0%BC%D0%B0%D1%8E%D1%82%D1%81%D1%8F%20%D0%BF%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%D0%BE%D0%B2%D1%8B%D0%B5%20%D1%80%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B2%20%D0%B3%D0%B5%D0%B9%D0%BC%D0%B4%D0%B5%D0%B2%D0%B5."
    "&location=CDT%20Hub%2C%20Kneza%20Milo%C5%A1a%2012%2C%206%20sprat%2C%20Belgrade"
)
GOOGLE_CAL_URL = os.getenv("GOOGLE_CAL_URL") or DEFAULT_GOOGLE_CAL_URL
APPLE_CAL_URL = os.getenv("APPLE_CAL_URL", "").strip()

serbia_tz = pytz.timezone("Europe/Belgrade")

# Напоминания:
# 1) за сутки, 25 фев в 15:00
# 2) за 3 часа, 26 фев в 15:00
REMINDER1_DT = datetime(2026, 2, 25, 15, 0, tzinfo=serbia_tz)
REMINDER2_DT = datetime(2026, 2, 26, 15, 0, tzinfo=serbia_tz)

MAPS_URL = "https://www.google.com/maps/search/?api=1&query=CDT%20Hub%2C%20Kneza%20Milo%C5%A1a%2012%2C%20Belgrade"

CONFIRMED_COL = 10  # J

# -----------------
# GOOGLE SHEETS
# -----------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# -----------------
# BOT
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
    """Возвращает номер строки (1-based) где user_id, или None."""
    col = sheet.col_values(1)  # A: user_id
    for idx, val in enumerate(col[1:], start=2):  # пропускаем заголовок
        if str(val) == str(user_id):
            return idx
    return None


def update_confirmed(user_id: int, value: str) -> bool:
    """
    Пишет confirmed в колонку J (10).
    Возвращает True если нашли строку и обновили, иначе False.
    """
    row = find_user_row(user_id)
    if row is None:
        return False
    sheet.update_cell(row, CONFIRMED_COL, value)
    return True


def build_calendar_kb():
    kb = InlineKeyboardBuilder()
    if GOOGLE_CAL_URL:
        kb.row(types.InlineKeyboardButton(text="🗓 Google Календарь", url=GOOGLE_CAL_URL))
    if APPLE_CAL_URL:
        kb.row(types.InlineKeyboardButton(text="🍎 Apple Календарь", url=APPLE_CAL_URL))
    return kb.as_markup() if kb.buttons else None


def build_confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✅ Я буду!", callback_data="confirm_yes"))
    kb.row(types.InlineKeyboardButton(text="❌ Изменились планы", callback_data="confirm_no"))
    return kb.as_markup()


# -----------------
# REGISTRATION FLOW
# -----------------
@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await message.answer(
        "Здравствуйте! 👋\n\n"
        "Вы регистрируетесь на митап от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве».\n\n"
        "(1/7) Введите ваши имя и фамилию:"
    )
    await state.set_state(Registration.full_name)


@dp.message(Registration.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer("(2/7) Введите ваш e-mail:")
    await state.set_state(Registration.email)


@dp.message(Registration.email)
async def process_email(message: types.Message, state: FSMContext):
    if "@" not in message.text:
        await message.answer("Пожалуйста, введите корректный e-mail (с символом @):")
        return

    await state.update_data(email=message.text.strip())

    kb = ReplyKeyboardBuilder()
    directions = [
        "🎮 Game Design",
        "📊 Product / Analytics",
        "🎨 Art / Design",
        "💻 Development",
        "📢 Marketing",
        "🧪 QA",
        "🧠 Management / Lead",
        "📚 HR / Recruitment",
        "✏️ Другое",
    ]
    for d in directions:
        kb.add(types.KeyboardButton(text=d))

    await message.answer(
        "(3/7) В каком направлении вы сейчас работаете?",
        reply_markup=kb.adjust(2).as_markup(resize_keyboard=True)
    )
    await state.set_state(Registration.position)


@dp.message(Registration.position)
async def process_position(message: types.Message, state: FSMContext):
    if message.text.strip() == "✏️ Другое":
        await message.answer(
            "Пожалуйста, укажите ваше направление вручную:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Registration.custom_position)
        return

    await state.update_data(position=message.text.strip())
    await message.answer("(4/7) В какой компании вы работаете?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.company)


@dp.message(Registration.custom_position)
async def process_custom_position(message: types.Message, state: FSMContext):
    await state.update_data(position=message.text.strip())
    await message.answer("(4/7) В какой компании вы работаете?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.company)


@dp.message(Registration.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text.strip())

    kb = ReplyKeyboardBuilder()
    for i in ["нет опыта", "менее 1 года", "1-3 года", "3-6 лет", "более 6 лет"]:
        kb.add(types.KeyboardButton(text=i))

    await message.answer(
        "(5/7) Ваш опыт работы в геймдеве:",
        reply_markup=kb.adjust(2).as_markup(resize_keyboard=True)
    )
    await state.set_state(Registration.experience)


@dp.message(Registration.experience)
async def process_experience(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text.strip())

    kb = ReplyKeyboardBuilder()
    kb.add(types.KeyboardButton(text="Да"))
    kb.add(types.KeyboardButton(text="Нет"))

    await message.answer(
        "(6/7) Вы рассматриваете новые рабочие предложения?",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(Registration.job_search)


@dp.message(Registration.job_search)
async def process_job_search(message: types.Message, state: FSMContext):
    await state.update_data(job_search=message.text.strip())

    kb = ReplyKeyboardBuilder()
    kb.add(types.KeyboardButton(text="Да"))
    kb.add(types.KeyboardButton(text="Нет"))

    await message.answer(
        "(7/7) Знали ли вы про компанию G5 Games ранее?",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(Registration.know_g5)


@dp.message(Registration.know_g5)
async def finish(message: types.Message, state: FSMContext):
    await state.update_data(know_g5=message.text.strip())
    data = await state.get_data()

    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else ""

    row = find_user_row(user_id)
    values = [
        user_id,
        username,
        data.get("full_name", ""),
        data.get("email", ""),
        data.get("position", ""),
        data.get("company", ""),
        data.get("experience", ""),
        data.get("job_search", ""),
        data.get("know_g5", ""),
        "",  # confirmed
    ]

    if row is None:
        sheet.append_row(values)
    else:
        sheet.update(f"A{row}:J{row}", [values])

    await message.answer(
        f"{data.get('full_name','')}, спасибо за регистрацию! 🎉\n\n"
        "Ждем вас на митапе от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве»\n\n"
        "📅 26 февраля, 18:00\n"
        "📍 Белград, <a href=\"https://www.google.com/maps/search/?api=1&query=CDT%20Hub%2C%20Kneza%20Milo%C5%A1a%2012%2C%20Belgrade\">CDT Hub, Кнеза Милоша 12, 6 этаж</a>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

    cal_kb = build_calendar_kb()
    if cal_kb:
        await message.answer("Добавьте событие в календарь:", reply_markup=cal_kb)

    await state.clear()


# -----------------
# TEST COMMAND (ручной тест кнопок подтверждения)
# -----------------
@dp.message(F.text == "/test_confirm")
async def test_confirm(message: types.Message):
    await message.answer(
        "🔔 Тест: сможете ли вы прийти?",
        reply_markup=build_confirm_kb()
    )


# -----------------
# CONFIRM CALLBACKS
# -----------------
@dp.callback_query(F.data.in_(["confirm_yes", "confirm_no"]))
async def confirm_attendance(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    ok = False
    if callback.data == "confirm_no":
        ok = update_confirmed(user_id, "no")
        msg = (
            "Понимаем, планы меняются 🙂\n"
            "Спасибо, что предупредили!\n\n"
            "Следите за анонсами будущих митапов в @g5careers."
        )
    else:
        ok = update_confirmed(user_id, "yes")
        msg = (
            "Отлично! Мы отметили, что вы придете.\n"
            "До встречи на митапе 👋"
        )

    if not ok:
        # на всякий случай: если нажали кнопку без регистрации
        msg = "Кажется, вы ещё не зарегистрировались через бота. Нажмите /start 🙂"

    await callback.message.answer(msg)
    await callback.answer()


# -----------------
# REMINDERS
# -----------------
async def reminder_1_confirm():
    # всем, кто зарегистрирован и не отказался (confirmed != "no")
    users = sheet.get_all_records()  # читает по заголовкам
    text = (
        "🔔 Уже завтра митап от G5 Games: «Продукт и маркетинг в геймдеве»\n\n"
        "📅 26 февраля, 18:00\n"
        "📍 CDT Hub, Кнеза Милоша 12, 6 этаж\n\n"
        "Подскажите, пожалуйста, сможете ли вы прийти?"
    )
    kb = build_confirm_kb()

    for u in users:
        try:
            uid = int(u.get("user_id"))
        except Exception:
            continue

        if (u.get("confirmed") or "").strip().lower() == "no":
            continue

        try:
            await bot.send_message(uid, text, reply_markup=kb)
            await asyncio.sleep(0.05)
        except Exception:
            pass


async def reminder_2_final():
    # только тем, кто подтвердил (confirmed == "yes")
    users = sheet.get_all_records()
    text = (
        "🚀 Мы начинаем сегодня в 18:00 — продуктовый митап от G5 Games\n"
        f"До скорой встречи в CDT Hub!\n\n🗺 {MAPS_URL}"
    )

    for u in users:
        try:
            uid = int(u.get("user_id"))
        except Exception:
            continue

        if (u.get("confirmed") or "").strip().lower() != "yes":
            continue

        try:
            await bot.send_message(uid, text)
            await asyncio.sleep(0.05)
        except Exception:
            pass


# -----------------
# MAIN
# -----------------
async def main():
    print("MAIN: start")

    await bot.delete_webhook(drop_pending_updates=True)
    print("MAIN: webhook cleared")

    scheduler.add_job(reminder_1_confirm, "date", run_date=REMINDER1_DT)
    scheduler.add_job(reminder_2_final, "date", run_date=REMINDER2_DT)
    print("MAIN: jobs added")

    scheduler.start()
    print("MAIN: scheduler started")

    me = await bot.get_me()
    print(f"MAIN: bot is @{me.username} (id={me.id})")
    print("MAIN: polling...")

    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
