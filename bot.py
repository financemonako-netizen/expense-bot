import os
import telebot
from flask import Flask, request
from google.oauth2.service_account import Credentials
import gspread

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ================== GOOGLE ==================
scopes = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']

creds = Credentials.from_service_account_file(
    "credentials.json", scopes=scopes)

gc = gspread.authorize(creds)
sh = gc.open_by_url(SPREADSHEET_URL)
sheet = sh.sheet1

drive_service = build('drive', 'v3', credentials=creds)

user_states = {}

# ================== МЕНЮ ==================
def main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💸 Добавить расход")
    return markup

# ================== START ==================
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
                     "👋 Привет! Нажми кнопку ниже:",
                     reply_markup=main_menu())

# ================== ДОБАВИТЬ РАСХОД ==================
@bot.message_handler(func=lambda m: m.text == "💸 Добавить расход")
def add_expense(message):
    user_states[message.chat.id] = {"state": "amount", "data": {}}
    bot.send_message(message.chat.id, "Введите сумму:")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id

    if chat_id not in user_states:
        return

    state = user_states[chat_id]["state"]

    if state == "amount":
        try:
            amount = float(message.text.replace(",", "."))
            user_states[chat_id]["data"]["amount"] = amount
            user_states[chat_id]["state"] = "description"
            bot.send_message(chat_id, "Введите описание:")
        except:
            bot.send_message(chat_id, "Введите число!")

    elif state == "description":
        user_states[chat_id]["data"]["description"] = message.text
        user_states[chat_id]["state"] = "photo"
        bot.send_message(chat_id, "Отправьте фото чека или напишите 'нет'")

    elif state == "photo":
        if message.text.lower() == "нет":
            save_to_google(chat_id, "-")
        else:
            bot.send_message(chat_id, "Отправьте фото как изображение")

# ================== ФОТО ==================
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id

    if chat_id not in user_states:
        return

    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    file_stream = io.BytesIO(downloaded_file)

    file_metadata = {
        'name': f"receipt_{datetime.datetime.now().timestamp()}.jpg",
        'parents': [DRIVE_FOLDER_ID]
    }

    media = MediaIoBaseUpload(file_stream, mimetype='image/jpeg')

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    save_to_google(chat_id, file.get("webViewLink"))

# ================== СОХРАНЕНИЕ ==================
def save_to_google(chat_id, photo_link):
    data = user_states[chat_id]["data"]

    row = [
        datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        data.get("amount"),
        data.get("description"),
        photo_link
    ]

    sheet.append_row(row)

    bot.send_message(chat_id, "✅ Сохранено!", reply_markup=main_menu())
    del user_states[chat_id]

# ================== WEBHOOK ==================
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running"

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{os.environ.get('RENDER_EXTERNAL_URL')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=10000)
