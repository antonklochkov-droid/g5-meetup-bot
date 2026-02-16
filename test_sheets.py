import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

SHEET_NAME = "G5 Event Registrations"  # ← у тебя так называется таблица

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
client = gspread.authorize(creds)

sheet = client.open(SHEET_NAME).sheet1
sheet.append_row(["TEST", str(datetime.now())])

print("OK: строка добавлена")
