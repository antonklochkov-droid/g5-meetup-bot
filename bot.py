import os
import base64
import json
import asyncio
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
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

PHOTO_LINK = "ССЫЛКА_НА_ФОТО"

# Прямая ссылка на картинку (или Telegram file_id)
REMINDER_IMAGE_URL = "https://your-image-url.com/image.jpg"

BELGRADE_TZ = timezone("Europe/Belgrade")


def get_gspread_client():
    try:
        encoded_json = os.getenv("SERVICE_ACCOUNT_B64")
        if not encoded_json:
            logging.error("SERVICE_ACCOUNT_B64 is not set")
            return None

        decoded_json = json.loads(base64.b64decode(encoded_json.strip()))
        creds = Credentials.from_service_account_info(
            decoded_json,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
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


class Feedback(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=BELGRADE_TZ)

# --- РЕГИСТРАЦИЯ ---


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте!\nВы регистрируетесь на митап от G5 Games:\n"
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

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Game Design"), KeyboardButton(text="Product / Analytics")],
            [KeyboardButton(text="Art / Design"), KeyboardButton(text="Development")],
            [KeyboardButton(text="Marketing"), KeyboardButton(text="QA")],
            [KeyboardButton(text="Management / Lead"), KeyboardButton(text="HR / Recruitment")],
            [KeyboardButton(text="Другое")],
        ],
        resize_keyboard=True,
    )
    await message.answer("(3/7) В каком направлении вы сейчас работаете?", reply_markup=kb)
    await state.set_state(Registration.direction)


@dp.message(Registration.direction)
async def process_direction(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if text == "Другое":
        await message.answer("Пожалуйста, укажите ваше направление вручную:")
        await state.set_state(Registration.custom_direction)
        return

    await state.update_data(direction=text)
    await ask_company(message, state)


@dp.message(Registration.custom_direction)
async def process_custom_direction(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text.strip())
    await ask_company(message, state)


async def ask_company(message: types.Message, state: FSMContext):
    await message.answer("(4/7) В какой компании вы работаете?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Registration.company)


@dp.message(Registration.company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(company=message.text.strip())

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="нет опыта"), KeyboardButton(text="менее 1 года")],
            [KeyboardButton(text="1-3 года"), KeyboardButton(text="3-6 лет")],
            [KeyboardButton(text="более 6 лет")],
        ],
        resize_keyboard=True,
    )
    await message.answer("(5/7) Ваш опыт работы в геймдеве:", reply_markup=kb)
    await state.set_state(Registration.experience)


@dp.message(Registration.experience)
async def process_exp(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text.strip())

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]],
        resize_keyboard=True,
    )
    await message.answer("(6/7) Вы рассматриваете новые рабочие предложения?", reply_markup=kb)
    await state.set_state(Registration.job_offers)


@dp.message(Registration.job_offers)
async def process_offers(message: types.Message, state: FSMContext):
    await state.update_data(job_offers=message.text.strip())

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]],
        resize_keyboard=True,
    )
    await message.answer("(7/7) Знали ли вы про компанию G5 Games ранее?", reply_markup=kb)
    await state.set_state(Registration.known_g5)


@dp.message(Registration.known_g5)
async def finish_reg(message: types.Message, state: FSMContext):
    await state.update_data(known_g5=message.text.strip())

    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"

    try:
        client = get_gspread_client()
        if client:
            sheet = client.open(SHEET_NAME).get_worksheet(0)
            sheet.append_row(
                [
                    str(user_id),
                    username,
                    data.get("full_name", ""),
                    data.get("email", ""),
                    data.get("direction", ""),
                    data.get("company", ""),
                    data.get("experience", ""),
                    data.get("job_offers", ""),
                    data.get("known_g5", ""),
                    "Wait",
                ]
            )
    except Exception as e:
        logging.error(f"Write error: {e}")

    cal_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Google Календарь", url=GOOGLE_CAL)],
            [InlineKeyboardButton(text="Apple Календарь", url=APPLE_CAL)],
        ]
    )

    await message.answer(
        f"{data.get('full_name')}, спасибо за регистрацию!\n"
        "Ждем вас на митапе от G5 Games:\n"
        "«Продукт и маркетинг в геймдеве»\n"
        "26 февраля в 18:00, Кнеза Милоша 12 (CDT Hub).\n\n"
        "Добавьте событие в календарь:",
        reply_markup=cal_kb,
    )

    await message.answer("Вы можете закрыть меню кнопкой ниже.", reply_markup=ReplyKeyboardRemove())
    await state.clear()


# --- ЛОГИКА ОПРОСА ---


@dp.callback_query(F.data == "start_feedback")
async def feedback_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=str(i)) for i in range(1, 6)],
            [KeyboardButton(text=str(i)) for i in range(6, 11)],
        ],
        resize_keyboard=True,
    )
    await callback.message.answer(
        "(1/5) Какое у вас общее впечатление от мероприятия?\n"
        "(1 — совсем не понравился, 10 — очень понравился)",
        reply_markup=kb,
    )
    await state.set_state(Feedback.q1)


@dp.callback_query(F.data == "decline_feedback")
async def feedback_decline(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "В любом случае рады, что вы провели этот вечер с G5 Games.\n"
        "Скоро поделимся фотографиями и материалами с митапа — будем на связи!"
    )


@dp.message(Feedback.q1)
async def feedback_q1(message: types.Message, state: FSMContext):
    await state.update_data(q1=message.text.strip())
    await message.answer(
        "(2/5) Оцените выступление Екатерины Быстрых с темой "
        "«Главные тренды: что будет с мобильными играми в 2026?»\n"
        "(1 — совсем не понравилось, 10 — очень понравилось)"
    )
    await state.set_state(Feedback.q2)


@dp.message(Feedback.q2)
async def feedback_q2(message: types.Message, state: FSMContext):
    await state.update_data(q2=message.text.strip())
    await message.answer(
        "(3/5) Оцените выступление Максима Мишанского с темой "
        "«Топ ошибок продакт-менеджера в геймдеве, которые стоят времени и денег»\n"
        "(1 — совсем не понравилось, 10 — очень понравилось)"
    )
    await state.set_state(Feedback.q3)


@dp.message(Feedback.q3)
async def feedback_q3(message: types.Message, state: FSMContext):
    await state.update_data(q3=message.text.strip())
    await message.answer(
        "(4/5) Оцените организацию мероприятия и работу ивент-команды\n"
        "(1 — совсем не понравилась, 10 — очень понравилась)"
    )
    await state.set_state(Feedback.q4)


@dp.message(Feedback.q4)
async def feedback_q4(message: types.Message, state: FSMContext):
    await state.update_data(q4=message.text.strip())
    await message.answer(
        "(5/5) Если у вас есть комментарии, замечания или предложения — будем рады вашему мнению",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Feedback.q5)


# --- ПОДТВЕРЖДЕНИЕ ПРИСУТСТВИЯ ---


async def update_status(user_id: int, status: str):
    try:
        client = get_gspread_client()
        if not client:
            return
        sheet = client.open(SHEET_NAME).get_worksheet(0)
        cell = sheet.find(str(user_id))
        sheet.update_cell(cell.row, 10, status)  # J confirmed
    except Exception as e:
        logging.error(f"Status update error: {e}")


async def update_feedback(user_id: int, answers: dict):
    try:
        client = get_gspread_client()
        if not client:
            return
        sheet = client.open(SHEET_NAME).get_worksheet(0)
        cell = sheet.find(str(user_id))
        row = cell.row

        sheet.update_cell(row, 11, answers.get("q1", ""))
        sheet.update_cell(row, 12, answers.get("q2", ""))
        sheet.update_cell(row, 13, answers.get("q3", ""))
        sheet.update_cell(row, 14, answers.get("q4", ""))
        sheet.update_cell(row, 15, answers.get("q5", ""))
    except Exception as e:
        logging.error(f"Feedback write error: {e}")


@dp.message(F.text == "✅ Я буду!")
async def confirm_yes(message: types.Message):
    await update_status(message.from_user.id, "Coming")
    await message.answer(
        "Отлично! Вы в списке участников.\nДо встречи на митапе 👋",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(F.text == "❌ Изменились планы")
async def confirm_no(message: types.Message):
    await update_status(message.from_user.id, "Declined")
    await message.answer(
        "Понимаем, планы меняются 🙂\nСпасибо, что предупредили!\n"
        "Следите за анонсами будущих митапов в канале @g5careers.",
        reply_markup=ReplyKeyboardRemove(),
    )


# --- ФУНКЦИИ РАССЫЛОК И НАПОМИНАНИЙ ---


async def send_reminder_24h():
    client = get_gspread_client()
    if not client:
        return

    sheet = client.open(SHEET_NAME).get_worksheet(0)
    records = sheet.get_all_values()

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Изменились планы"), KeyboardButton(text="✅ Я буду!")]],
        resize_keyboard=True,
    )

    text = (
        "🔔 Уже завтра митап от G5 Games: «Продукт и маркетинг в геймдеве»\n"
        "📅 26 февраля, 18:00\n"
        "📍 CDT Hub, Кнеза Милоша 12\n\n"
        "Подскажите, пожалуйста, планируете ли вы прийти?"
    )

    for row in records[1:]:
        try:
            user_id = int(row[0])
            await bot.send_photo(user_id, photo=REMINDER_IMAGE_URL, caption=text, reply_markup=kb)
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"send_reminder_24h error: {e}")


async def send_reminder_3h():
    client = get_gspread_client()
    if not client:
        return

    sheet = client.open(SHEET_NAME).get_worksheet(0)
    records = sheet.get_all_values()

    text = (
        "🚀 Сегодня в 18:00 — G5 Games Meetup «Продукт и маркетинг в геймдеве».\n"
        "Обсудим тренды мобильных игр, продуктовые решения и ошибки, которые стоят дорого.\n\n"
        "До скорой встречи в CDT Hub!"
    )

    for row in records[1:]:
        try:
            user_id = int(row[0])
            status = row[9] if len(row) > 9 else "Wait"
            if status in ["Coming", "Wait"]:
                await bot.send_message(user_id, text)
                await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"send_reminder_3h error: {e}")


async def send_feedback_request():
    client = get_gspread_client()
    if not client:
        return

    sheet = client.open(SHEET_NAME).get_worksheet(0)
    records = sheet.get_all_values()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, хочу", callback_data="start_feedback")],
            [InlineKeyboardButton(text="Нет, спасибо", callback_data="decline_feedback")],
        ]
    )

    for row in records[1:]:
        try:
            user_id = int(row[0])
            status = row[9] if len(row) > 9 else "Wait"
            if status in ["Coming", "Wait"]:
                await bot.send_message(
                    user_id,
                    "Спасибо, что были с нами на G5 Games Meetup 💙\n\nХотите оставить фидбек?",
                    reply_markup=kb,
                )
                await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"send_feedback_request error: {e}")


async def send_photos_link():
    client = get_gspread_client()
    if not client:
        return

    sheet = client.open(SHEET_NAME).get_worksheet(0)
    records = sheet.get_all_values()

    msg = f"📸 Фото с G5 Games Meetup уже доступны!\n\nСсылка: {PHOTO_LINK}"

    for row in records[1:]:
        try:
            user_id = int(row[0])
            status = row[9] if len(row) > 9 else "Wait"
            if status in ["Coming", "Wait"]:
                await bot.send_message(user_id, msg)
                await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"send_photos_link error: {e}")


@dp.message(Feedback.q5)
async def feedback_finish(message: types.Message, state: FSMContext):
    await state.update_data(q5=message.text.strip())
    data = await state.get_data()
    await update_feedback(message.from_user.id, data)
    await message.answer("Спасибо за ваши ответы! Это поможет нам стать лучше. 💙")
    await state.clear()


# --- HEALTHCHECK ---


async def handle_hc(request):
    return web.Response(text="OK")


async def main():
    app = web.Application()
    app.router.add_get("/", handle_hc)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    asyncio.create_task(site.start())

    # --- РАСПИСАНИЕ (Тестовые даты на 18 февраля) ---
    scheduler.add_job(send_reminder_24h, "cron", year=2026, month=2, day=18, hour=12, minute=40)
    scheduler.add_job(send_reminder_3h, "cron", year=2026, month=2, day=18, hour=12, minute=45)
    scheduler.add_job(send_feedback_request, "cron", year=2026, month=2, day=18, hour=12, minute=50)
    scheduler.add_job(send_photos_link, "cron", year=2026, month=2, day=18, hour=13, minute=0)

    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())