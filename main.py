import logging
import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaPhoto, KeyboardButton, ReplyKeyboardRemove, InputMediaVideo
import telegram
import random
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from dotenv import load_dotenv
import gspread
from google.oauth2 import service_account
# from new_form import get_new_form_conversation_handler  # Will be uncommented when file is ready

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8358942377:AAEVJKtj3SCAOhgKzvFqynrjFH_kabcKbpM"

ADMIN_CHAT_ID = "YOUR_ADMIN_CHAT_ID"

CHANNEL_ID = "-1002949398344"

APPLICATIONS_CHANNEL_ID = "-1003149841343"

SHEET_ID = "131rn3rImb7vBLTjSGggswfjSK91GNIbrc-4bA5LKZcc"

SHEET_CREDENTIALS = "telegram-bot-sheet-access-eba0358ee229.json"

(FORM_NAME, FORM_BIRTH_DATE, FORM_CITIZENSHIP, FORM_LOCATION, FORM_CONTACT, 
 FORM_WORK_SEEKING, FORM_PASSPORT, FORM_VISA_DOCS, FORM_DIFFICULTIES, 
 FORM_READY_SPEED, FORM_FINANCIAL_ABILITY, FORM_IMMEDIATE_START, FORM_VISA_TERM) = range(13)

# Стани для візової анкети (35 станів: welcome + 30 питань + 4 додаткових стани)
(VISA_FORM_WELCOME, VISA_Q1, VISA_Q2, VISA_Q3, VISA_Q4, VISA_Q5, VISA_Q6, VISA_Q7, VISA_Q8, VISA_Q9, VISA_Q10,
 VISA_Q11, VISA_Q12, VISA_Q13, VISA_Q14, VISA_Q15, VISA_Q16, VISA_Q17, VISA_Q18, VISA_Q19, VISA_Q20,
 VISA_Q21, VISA_Q22, VISA_Q23, VISA_Q24, VISA_Q25, VISA_Q26, VISA_Q27, VISA_Q28, VISA_Q29, VISA_Q30,
 VISA_Q14_DETAIL, VISA_Q15_DETAIL, VISA_Q23_DETAIL, VISA_Q28_DETAIL) = range(35)

submitted_applications = set()

async def safe_edit_message(query, text, reply_markup=None, parse_mode='HTML'):
    """Безпечне редагування повідомлення. Якщо не виходить - видаляє і відправляє нове"""
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except:
        await query.message.delete()
        await query.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

async def check_subscription(bot, user_id):
    """Проверяет подписан ли пользователь на канал"""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

async def send_subscription_message(update, context):
    """Отправляет сообщение с просьбой подписаться на канал"""
    subscription_text = f"""🔥 <b>Лучшие вакансии — только для подписчиков!</b>

Мы публикуем самые свежие и выгодные предложения работы в канале Центр Трудоустройства | раньше, чем где-либо ещё.

<b>Подпишитесь сейчас, чтобы не пропустить шанс на отличную работу!</b>

После подписки нажмите «✅ Я подписался» и продолжайте."""
    
    keyboard = [
        [InlineKeyboardButton("📢 Перейти к каналу", url=f"https://t.me/+xG5QAaLGbT03NDky")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")]
    ]
    
    await update.message.reply_text(
        subscription_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    ,
            protect_content=True
        )

COUNTRIES = {
    "switzerland": {"name": "🇨🇭 Швейцария", "file": "vacancies_switzerland.json"},
    "norway": {"name": "🇳🇴 Норвегия", "file": "vacancies_norway.json"},
    "england": {"name": "🇬🇧 Англия", "file": "vacancies_england.json"},
    "germany": {"name": "🇩🇪 Германия", "file": "vacancies_germany.json"},
    "poland": {"name": "🇵🇱 Польша", "file": "vacancies_poland.json"},
    "france": {"name": "🇫🇷 Франция", "file": "vacancies_france.json"},
    "canada": {"name": "🇨🇦 Канада", "file": "vacancies_canada.json"}
}

def load_qa():
    """Загружает вопросы и ответы из файла"""
    try:
        with open("qa.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

def load_certificates():
    """Загружает сертификаты из файла"""
    try:
        with open("certificates.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

def load_visas():
    """Загружает визы из файла"""
    try:
        with open("visas.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

def load_vacancies(country_code):
    """Загружает вакансии для конкретной страны"""
    try:
        filename = COUNTRIES[country_code]["file"]
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Файл {filename} не найден")
        return []
    except json.JSONDecodeError:
        logger.error(f"Ошибка чтения JSON из файла {filename}")
        return []

def load_reviews():
    """Загружает отзывы из файла"""
    try:
        with open("reviews.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

async def check_video_availability(video_url):
    """Проверяет доступность видео по URL"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.head(video_url) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'video' in content_type:
                        logger.info(f"✅ Видео доступно: {video_url} (статус: {response.status}, тип: {content_type})")
                        return True
                    else:
                        logger.warning(f"⚠️ Файл доступно, но не является видео: {video_url} (тип: {content_type})")
                        return False
                else:
                    logger.warning(f"❌ Видео недоступно: {video_url} (статус: {response.status})")
                    return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки видео {video_url}: {str(e)}")
        return False

async def download_and_send_video(context, chat_id, video_url, caption, reply_markup):
    """Загружает видео локально и отправляет как файл"""
    try:
        import aiohttp
        import tempfile
        import os
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                        async for chunk in response.content.iter_chunked(8192):
                            temp_file.write(chunk)
                        temp_file_path = temp_file.name
                    
                    try:
                        with open(temp_file_path, 'rb') as video_file:
                            await context.bot.send_video(
                                chat_id=chat_id,
                                video=video_file,
                                caption=caption,
                                reply_markup=reply_markup,
                                parse_mode='HTML',
            protect_content=True
                            )
                        logger.info("✅ Видео загружено локально и отправлено")
                        return True
                    finally:
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass
                else:
                    logger.error(f"❌ Ошибка загрузки файлу: статус {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки как файл: {str(e)}")
        return False

async def find_next_available_review(context, query, start_review_id, reviews):
    """Находит следующий доступный отзыв"""
    logger.info(f"🔍 Поиск следующего доступного отзыва, начиная с {start_review_id+1}")
    
    for i in range(len(reviews)):
        current_id = (start_review_id + i + 1) % len(reviews)
        review = reviews[current_id]
        
        try:
            logger.info(f"🎬 Попробуем загрузить отзыв {current_id+1} (ID: {review['id']}) по URL: {review['video']}")
            
            success = False
            for attempt in range(2):
                try:
                    if attempt == 0:
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=review['video'],
                            caption=f"⭐ <b>Отзывы наших клиентов</b>",
                            reply_markup=get_reviews_menu(current_id, len(reviews)),
                            parse_mode='HTML',
            protect_content=True
        )
                    else:
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=review['video'],
                            caption=f"⭐ <b>Отзывы наших клиентов</b>",
                            reply_markup=get_reviews_menu(current_id, len(reviews)),
                            parse_mode='HTML',
            protect_content=True
        )
                    
                    success = True
                    logger.info(f"✅ Успешно загружен отзыв {current_id+1} (попытка {attempt+1})")
                    return
                    
                except Exception as e:
                    logger.warning(f"⚠️ Попытка {attempt+1} неудачна для отзыва {current_id+1}: {str(e)}")
                    if attempt < 1:
                        await asyncio.sleep(0.5)
                    continue
            
            if not success:
                logger.error(f"❌ Все попытки неудачны для отзыва {current_id+1}")
                continue
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка загрузки отзыва {current_id+1}: {str(e)}")
            continue
    
    logger.error("❌ Не найдено ни одного доступного отзыва")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⭐ <b>Отзывы наших клиентов</b>\n\nВсе видео временно недоступны.",
        parse_mode='HTML',
            protect_content=True
        )

def get_sheet_client():
    """Подключается к Google Sheets"""
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(
            SHEET_CREDENTIALS, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

def check_user_submitted(user_id):
    """Проверяет есть ли user_id уже в Google Sheets та чи заповнив він попередню анкету"""
    # Тепер перевіряємо чи є "заполнил" в колонці Предварительная анкета
    return check_user_filled_form(user_id)

def get_column_index_for_user_id(user_id):
    """Знайти індекс рядка для користувача в таблиці"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return None
        
        all_values = sheet.get_all_values()
        
        for i, row in enumerate(all_values[1:], start=2):  # Починаємо з рядка 2 (індекс 2)
            if len(row) > 0 and str(user_id) == str(row[0]):  # Колонка 0 = ТГ ID
                return i
        return None
    except Exception as e:
        logger.error(f"Помилка пошуку користувача в таблиці: {e}")
        return None

def add_user_to_sheet(user_id):
    """Додати нового користувача в таблицю після /start"""
    try:
        # Перевіряємо чи вже є в таблиці
        if get_column_index_for_user_id(user_id) is not None:
            return True
        
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        # Створюємо новий рядок
        new_row = [str(user_id), "7"] + [''] * 20  # ID, "7", і пусті колонки
        
        sheet.append_row(new_row)
        logger.info(f"Додано нового користувача {user_id} в таблицю")
        return True
    except Exception as e:
        logger.error(f"Помилка додавання користувача в таблицю: {e}")
        return False

def get_reminder_days(user_id):
    """Отримати скільки днів залишилось до наступного нагадування"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return 0
        
        row_index = get_column_index_for_user_id(user_id)
        if row_index is None:
            return 0
        
        value = sheet.cell(row_index, 2).value  # Колонка 1 (індекс 2) = Последнее напоминание
        return int(value) if value and value.strip() else 0
    except Exception as e:
        logger.error(f"Помилка отримання днів нагадування: {e}")
        return 0

def update_reminder_days(user_id, days):
    """Оновити скільки днів залишилось до наступного нагадування"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        row_index = get_column_index_for_user_id(user_id)
        if row_index is None:
            return False
        
        sheet.update_cell(row_index, 2, str(days))  # Колонка 1 (індекс 2) = Последнее напоминание
        return True
    except Exception as e:
        logger.error(f"Помилка оновлення днів нагадування: {e}")
        return False

def get_all_users_for_notifications():
    """Отримати всі user_id з таблиці для нагадувань"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return []
        
        all_values = sheet.get_all_values()
        user_ids = []
        
        for row in all_values[1:]:  # Пропускаємо заголовок
            if len(row) > 0 and row[0].strip():  # Колонка 0 = ТГ ID
                try:
                    user_ids.append(int(row[0]))
                except ValueError:
                    continue
        
        return user_ids
    except Exception as e:
        logger.error(f"Помилка отримання user_id з таблиці: {e}")
        return []

def check_user_filled_form(user_id):
    """Проверяет заполнил ли пользователь предварительную анкету (колонка Предварительная анкета)"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        all_values = sheet.get_all_values()
        
        # Знаходимо індекс колонки "Предварительная анкета" (передостання колонка перед Визовая анкета)
        for row in all_values[1:]:
            if len(row) > 0 and str(user_id) == str(row[0]):
                # Перевіряємо колонку R (індекс 17) = Предварительная анкета
                if len(row) > 17 and str(row[17]).strip().lower() == "заполнил":
                    return True
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки анкеты в Google Sheets: {e}")
        return False

def check_user_filled_visa(user_id):
    """Проверяет заполнил ли пользователь визовую анкету (колонка S - Визовая анкета)"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        all_values = sheet.get_all_values()
        
        for row in all_values[1:]:
            if len(row) > 0 and str(user_id) == str(row[0]):
                # Перевіряємо колонку S (індекс 18) = Визовая анкета
                if len(row) > 18 and str(row[18]).strip().lower() == "заполнил":
                    return True
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки визовой анкеты в Google Sheets: {e}")
        return False

def save_visa_filled(user_id):
    """Записывает 'заполнил' в колонку S (Визовая анкета) для пользователя"""
    try:
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        row_index = get_column_index_for_user_id(user_id)
        if row_index is None:
            logger.error(f"Користувача {user_id} не знайдено в таблиці")
            return False
        
        # Колонка S (індекс 19) = Визовая анкета
        sheet.update_cell(row_index, 19, "заполнил")
        logger.info(f"Візова анкета збережена для користувача {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения визовой анкеты в Google Sheets: {e}")
        return False

def save_to_sheets(form_data):
    """Сохраняет данные заявки в Google Sheets в існуючий рядок користувача"""
    try:
        user_id = form_data.get('user_id', '')
        if not user_id:
            logger.error("Не вказано user_id")
            return False
        
        sheet = get_sheet_client()
        if sheet is None:
            return False
        
        # Знаходимо рядок користувача
        row_index = get_column_index_for_user_id(user_id)
        if row_index is None:
            logger.error(f"Користувача {user_id} не знайдено в таблиці")
            return False
        
        # Оновлюємо дані користувача
        # Колонка 2 (індекс 3) = Время заполнения
        sheet.update_cell(row_index, 3, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Колонки 3-18 (індекси 4-19) = дані з форми
        sheet.update_cell(row_index, 4, form_data.get('name', ''))
        sheet.update_cell(row_index, 5, form_data.get('birth_date', ''))
        sheet.update_cell(row_index, 6, form_data.get('citizenship', ''))
        sheet.update_cell(row_index, 7, form_data.get('location', ''))
        sheet.update_cell(row_index, 8, form_data.get('contact', ''))
        sheet.update_cell(row_index, 9, form_data.get('work_seeking', ''))
        sheet.update_cell(row_index, 10, form_data.get('passport', ''))
        sheet.update_cell(row_index, 11, form_data.get('visa_docs', ''))
        sheet.update_cell(row_index, 12, form_data.get('difficulties', ''))
        sheet.update_cell(row_index, 13, form_data.get('ready_speed', ''))
        sheet.update_cell(row_index, 14, form_data.get('financial_ability', ''))
        sheet.update_cell(row_index, 15, form_data.get('immediate_start', ''))
        sheet.update_cell(row_index, 16, form_data.get('visa_term', ''))
        sheet.update_cell(row_index, 17, form_data.get('vacancy_title', ''))
        
        # Колонка R (індекс 18) = Предварительная анкета
        sheet.update_cell(row_index, 18, "заполнил")
        
        logger.info(f"Дані анкети збережено для користувача {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения в Google Sheets: {e}")
        return False

async def send_to_channel(context, form_data):
    """Отправляет заявку в канал"""
    try:
        message = f"""📝 <b>Новая заявка</b>

<b>Вакансия:</b> {form_data.get('vacancy_title', 'Не указано')}

<b>ФИО:</b> {form_data.get('name', '')}
<b>Дата рождения:</b> {form_data.get('birth_date', '')}
<b>Гражданство:</b> {form_data.get('citizenship', '')}
<b>Где находится:</b> {form_data.get('location', '')}
<b>Контакт:</b> {form_data.get('contact', '')}

<b>Ищет работу:</b> {form_data.get('work_seeking', '')}
<b>Загранпаспорт:</b> {form_data.get('passport', '')}
<b>Виза:</b> {form_data.get('visa_docs', '')}
<b>Сложности:</b> {form_data.get('difficulties', '')}
<b>Готовность:</b> {form_data.get('ready_speed', '')}
<b>Финансы:</b> {form_data.get('financial_ability', '')}
<b>Сразу перейти:</b> {form_data.get('immediate_start', '')}
<b>Срок визы:</b> {form_data.get('visa_term', '')}

<b>ID:</b> {form_data.get('user_id', '')} | <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        await context.bot.send_message(
            chat_id=APPLICATIONS_CHANNEL_ID,
            text=message,
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")
        return False

def get_main_menu():
    keyboard = [
        ["🧾 Вакансии", "✅ Гарантии"],
        ["💬 Связаться с менеджером", "❓ Вопрос - ответ"],
        ["🔄 Как мы работаем", "ℹ️ О нас"],
        ["📍 Контакты"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def is_main_menu_text(text: str) -> bool:
    return text in {
        "🧾 Вакансии",
        "✅ Гарантии",
        "💬 Связаться с менеджером",
        "❓ Вопрос - ответ",
        "🔄 Как мы работаем",
        "ℹ️ О нас",
        "📍 Контакты",
    }

def get_countries_menu():
    keyboard = []
    for country_code, country_data in COUNTRIES.items():
        keyboard.append([InlineKeyboardButton(country_data["name"], callback_data=f"country_{country_code}")])
    return InlineKeyboardMarkup(keyboard)

def get_country_vacancies_menu(country_code):
    vacancies = load_vacancies(country_code)
    keyboard = []
    
    if vacancies:
        for vacancy in vacancies:
            keyboard.append([InlineKeyboardButton(vacancy["title"], callback_data=f"vacancy_{country_code}_{vacancy['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к странам", callback_data="countries")])
    return InlineKeyboardMarkup(keyboard)

def get_certificates_menu(certificate_id):
    certificates = load_certificates()
    keyboard = []
    
    if len(certificates) > 1:
        keyboard.append([
            InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"certificate_{certificate_id-1}"),
            InlineKeyboardButton("➡️ Следующий", callback_data=f"certificate_{certificate_id+1}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")])
    return InlineKeyboardMarkup(keyboard)

def get_visas_menu(visa_id):
    visas = load_visas()
    keyboard = []
    
    if len(visas) > 1:
        keyboard.append([
            InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"visa_{visa_id-1}"),
            InlineKeyboardButton("➡️ Следующая", callback_data=f"visa_{visa_id+1}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")])
    return InlineKeyboardMarkup(keyboard)

def get_guarantees_menu():
    keyboard = [
        [InlineKeyboardButton("📋 Визы", callback_data="guarantees_visas")],
        [InlineKeyboardButton("📜 Сертификаты", callback_data="guarantees_certificates")],
        [InlineKeyboardButton("⚖️ Законность", callback_data="guarantees_legality")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reviews_menu(review_id, total_reviews):
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"review_{review_id-1}"),
            InlineKeyboardButton("➡️ Следующий", callback_data=f"review_{review_id+1}")
        ],
        [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_qa_menu(qa_id):
    qa_list = load_qa()
    keyboard = []
    
    if len(qa_list) > 1:
        keyboard.append([
            InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"qa_{qa_id-1}"),
            InlineKeyboardButton("➡️ Следующий", callback_data=f"qa_{qa_id+1}")
        ])
    
    return InlineKeyboardMarkup(keyboard)

def get_manager_language_menu():
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Связаться с русскоязычным менеджером", callback_data="manager_ru")],
        [InlineKeyboardButton("🇬🇧 Contact an English-speaking manager", callback_data="manager_en")],
        [InlineKeyboardButton("🇩🇪 Kontakt mit deutschsprachigem Manager aufnehmen", callback_data="manager_de")],
        [InlineKeyboardButton("🇵🇱 Skontaktuj się z menedżerem mówiącym po polsku", callback_data="manager_pl")],
        [InlineKeyboardButton("🇫🇷 Contacter un manager francophone", callback_data="manager_fr")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_manager_back_menu():
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к выбору языка", callback_data="manager_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_guarantees_menu():
    keyboard = [
        [InlineKeyboardButton("⭐ Отзывы", callback_data="guarantees_reviews")],
        [InlineKeyboardButton("📄 Лицензия", callback_data="guarantees_license")],
        [InlineKeyboardButton("📷 Из жизни компании", callback_data="guarantees_life")],
        [InlineKeyboardButton("📋 Визы клиентов", callback_data="guarantees_visas")],
        [InlineKeyboardButton("📜 Сертификаты клиентов", callback_data="guarantees_certificates")],
        [InlineKeyboardButton("📝 Образец договора", callback_data="guarantees_contract")],
        [InlineKeyboardButton("⚖️ Законность", callback_data="guarantees_legality")],
        [InlineKeyboardButton("🛡️ Как не попасть на мошенников", callback_data="guarantees_scam")],
        [InlineKeyboardButton("🛡️ Политика конфиденциальности", callback_data="guarantees_privacy")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_workflow_menu():
    keyboard = [
        [InlineKeyboardButton("📄 Необходимые документы", callback_data="workflow_documents")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_documents_menu():
    keyboard = [
        [InlineKeyboardButton("1️⃣ Первый этап", callback_data="workflow_first_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_first_stage_menu():
    keyboard = [
        [InlineKeyboardButton("2️⃣ Второй этап", callback_data="workflow_second_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_second_stage_menu():
    keyboard = [
        [InlineKeyboardButton("3️⃣ Третий этап", callback_data="workflow_third_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_third_stage_menu():
    keyboard = [
        [InlineKeyboardButton("4️⃣ Четвертый этап", callback_data="workflow_fourth_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fourth_stage_menu():
    keyboard = [
        [InlineKeyboardButton("5️⃣ Пятый этап", callback_data="workflow_fifth_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fifth_stage_menu():
    keyboard = [
        [InlineKeyboardButton("6️⃣ Шестой этап", callback_data="workflow_sixth_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sixth_stage_menu():
    keyboard = [
        [InlineKeyboardButton("7️⃣ Седьмой этап", callback_data="workflow_seventh_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_seventh_stage_menu():
    keyboard = [
        [InlineKeyboardButton("8️⃣ Восьмой этап", callback_data="workflow_eighth_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_eighth_stage_menu():
    keyboard = [
        [InlineKeyboardButton("9️⃣ Девятый этап", callback_data="workflow_ninth_stage")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_about_menu(page_id, total_pages):
    keyboard = []
    
    nav_buttons = []
    if page_id > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"about_{page_id-1}"))
    
    if page_id < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"about_{page_id+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

def get_scam_info_menu(page_id):
    keyboard = []
    
    nav_buttons = []
    if page_id > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"scam_{page_id-1}"))
    
    if page_id < 3:
        nav_buttons.append(InlineKeyboardButton("➡️ Далее", callback_data=f"scam_{page_id+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")])
    
    return InlineKeyboardMarkup(keyboard)

def get_scam_info_text(page_id):
    """Возвращает список сообщений для страницы о мошенниках по номеру"""
    scam_info = [
        [
            """⚠️ <b>Важно! Ознакомьтесь перед подачей документов</b>

Чтобы не попасться на мошенников и понимать, как на самом деле выглядит процесс официального трудоустройства за границей, внимательно ознакомьтесь с приведённой ниже информацией.

⸻

<b>Основные признаки мошенничества</b>""",

            """<b>1️⃣ Трудоустройство невозможно только по фото загранпаспорта.</b>
Если у вас запрашивают лишь фотографию паспорта — это мошенничество.
Для оформления документов необходима полная проверка и подтверждение личности.

<b>2️⃣Недостоверные или завышенные обещания.</b>
Будьте внимательны к заявлениям о "гарантированном получении визы", "оформлении без участия клиента" или "ускоренных сроках без проверки".
Ни одна лицензированная компания или агентство не имеет права гарантировать получение визы, так как окончательное решение всегда принимает посольство или консульство соответствующей страны.

Любые подобные формулировки — признак недобросовестной деятельности или попытки ввести клиента в заблуждение.""",

            """<b>3️⃣Поддельные лицензии в электронном формате.</b>
Будьте внимательны: мошенники часто отправляют "лицензию" в виде PDF-файла, утверждая, что это официальный документ.
На самом деле такой формат не подтверждает подлинность —
официальные лицензии на трудоустройство выдаются исключительно на бумажном носителе, с оригинальной подписью, печатью и регистрационным номером.

📄 Настоящая лицензия должна быть распечатана и выдана уполномоченным государственным органом.

⚠️ Мошенники, как правило, не показывают лицензию на видео, потому что у них её просто нет.
Файл, который они присылают, чаще всего создан самостоятельно в текстовом редакторе и не имеет никакой юридической силы.""",

            """<b>4️⃣Отсутствие реального офиса и подтверждения деятельности.</b>
Мошенники часто утверждают, что работают в официальном офисе, но на деле ведут деятельность из дома или вовсе не имеют физического адреса.
Если агент или компания отказываются показать офис на видео, это серьёзный сигнал насторожиться.

📹 Попросите короткое видео, где видно офис (или хотя бы часть помещения), и слышно голос того менеджера, с которым вы общаетесь.
Отказ записать такое видео — один из явных признаков нечестности, ведь чаще всего мошенники просто не имеют офиса и скрывают своё реальное местоположение.

⚠️ Надёжные компании, наоборот, спокойно показывают свой офис, 
не избегая прямого визуального контакта с клиентом.""",

            """<b>5️⃣Гарантии 100% трудоустройства.</b>
Ни одна официальная компания не может гарантировать трудоустройство со 100% уверенностью, так как решение зависит от множества факторов:
 • результатов проверки ваших документов и соответствия требованиям работодателя;
 • результатов собеседования, на котором именно работодатель принимает решение — подходит кандидат или нет.

❗️Если вам говорят:

«Заполните анкету, пришлите паспорт — мы всё согласуем и гарантированно трудоустроим»

— это прямой признак мошенничества.
Ни одно честное агентство не может влиять на решение работодателя или обходить этапы собеседования и проверки документов.""",

            """<b>6️⃣Обещания трёхразового питания за счёт работодателя.</b>
Формулировки вроде:

«Работодатель обеспечивает трёхразовое питание»,
«Меню предусмотрено для мусульман или вегетарианцев»

— не соответствуют реальности.
Ни один официальный работодатель не предоставляет трёхразовое питание, потому что основная цель трудоустройства — выполнение работы, а не обеспечение сотрудников питанием.

✅ Максимум, что может предоставляться — небольшой обед, чай, кофе или лёгкие перекусы во время рабочего дня.

❌ Упоминания о "трёхразовом питании" — это один из признаков мошеннических схем, рассчитанных на введение кандидатов в заблуждение.""",

            """<b>7️⃣Показ договоров, контрактов или приглашений через исчезающие сообщения.</b>
Если вам показывают договор, контракт, job letter, приглашение или любые другие документы, которые якобы относятся лично к вам как к соискателю, через исчезающее сообщение (в кружочке) в Telegram или WhatsApp — это явный признак мошенничества.

📄 Обычно мошенники демонстрируют видео со столом и распечатанными бумагами, иногда даже с вашей фамилией, чтобы создать впечатление, будто документы действительно оформлены.
Однако:

• Любые документы, касающиеся лично вас, должны быть предоставлены в полном формате, чтобы вы могли с ними ознакомиться, подписать и получить копию;
 • Показ на видео не подтверждает подлинность и не означает, что документы существуют в действительности;
 • Ни одна честная компания не демонстрирует документы, относящиеся к кандидату, через исчезающие сообщения — это делается исключительно мошенниками, чтобы скрыть переписку и не оставить доказательств."""
        ],

        [
            """<b>8️⃣Виза выдается только после сдачи биометрии и лично соискателю.</b>
Виза оформляется только после прохождения биометрической процедуры — сдачи отпечатков пальцев, сканирования сетчатки глаза, либо обоих процедур одновременно, в зависимости от требований страны.

📄 После внесения биометрических данных в базу виза вклеивается исключительно в заграничный паспорт самого соискателя.
Она не может быть выдана или передана:
 • менеджеру,
 • агенту,
 • посреднику,
 • работодателю,
 • или любому третьему лицу.""",

            """❌ В процессе мошенники могут заявлять:

«Виза будет отправлена вам почтой, когда она будет готова»

— это абсолютная ложь. Виза в любом случае оформляется только лично и сразу после сдачи биометрии. Любые обещания отправки документа третьими лицами — явный признак мошенничества.

<b>9️⃣Отсутствие англоязычных кураторов или менеджеров.</b>
Если в компании нет сотрудников, способных общаться на английском языке, это может быть сигналом мошенничества.

📄 Чаще всего такое происходит, когда мошенник работает из дома и кроме родного языка не владеет английским. В этом случае кандидат не получает полноценной поддержки и информации.""",

            """✅ Надёжные агентства и работодатели обеспечивают:
 • наличие менеджеров, свободно говорящих на английском языке;
 • возможность передачи контакта англоязычному сотруднику, если основной менеджер не владеет языком;
 • консультации и ответы на вопросы кандидата на официальном языке страны трудоустройства.

💡 Пример: если человек направляется в Англию, логично, что менеджер должен свободно общаться на английском языке, либо компания предоставляет другого сотрудника, способного вести общение на английском.

❌ Отсутствие такой поддержки — типичный признак возможного мошенничества.""",

            """<b>🔟Видео с места работы и «демонстрация менеджера»</b>

Если вам присылают видео рабочего процесса со склада или фермы, на котором якобы показан менеджер компании, будьте крайне осторожны.

📄 Почему это признак мошенничества:
 • Любая официальная компания не позволяет снимать процесс работы внутри объектов (склады, производства, фермы). Это регулируется внутренними правилами и законами.
 • Даже обычный сотрудник подписывает соглашение о неразглашении, запрещающее фото- и видеосъёмку третьими лицами. Нарушение может привести к санкциям вплоть до депортации.
 • Менеджер или агент по трудоустройству не имеет права приходить на объект и снимать видео для демонстрации кандидатам.""",

            """💡 Как мошенники обходят это правило:
 • Они трудоустраиваются на объект, снимают видео незаконным способом и используют его для обмана будущих клиентов.
 • На видео часто показывают себя на фоне склада, пытаясь создать впечатление реальной работы компании.

❌ Вывод: если менеджер демонстрирует рабочее место через видео, особенно с собой на фоне склада, это почти наверняка мошенничество.

<b>1️⃣1️⃣Наличие лицензии у посредника или менеджера по трудоустройству</b>

Если человек представляется посредником и говорит, что:

«Я работаю сам на себя, у меня нет компании, я предоставляю услуги по трудоустройству»

— будьте крайне осторожны.""",

            """📌 Что нужно проверить:
 1. Лицензия обязательно — попросите показать её на видео;
 2. Если лицензии нет, такой человек не имеет права предоставлять услуги по трудоустройству;
 3. Ни один работодатель, ни одна компания, ни один склад не будут сотрудничать с таким посредником, потому что он неаккредитован и не имеет права вести набор работников;
 4. Отзывы или видео с места работы не заменяют официальной лицензии — это исключительно работа и подготовка ранее мошенника для подобных операций, направленная на убеждение будущих клиентов.

💡 Вывод:

Любой посредник или менеджер без официальной лицензии не имеет права заниматься трудоустройством. Все обещания, видео и отзывы в этом случае — прямой признак мошенничества.""",

            """<b>1️⃣2️⃣Завышение зарплат — признак мошенничества</b>

Мошенники часто обещают зарплаты от €5 000 или $5 000 и выше, чтобы привлечь кандидатов.

📌 На что обратить внимание:
 • Реальные средние зарплаты для приезжих с СНГ:
 • Германия: €2 500–€3 500/мес
 • Великобритания: £2 900/мес (~€3 400)
 • Польша: €1 000–€1 300/мес
 • Канада: CAD $33 000–$45 000/год (~€27 000–€38 000)
 • Норвегия: 45 000–55 000 NOK/мес (~€4 000–4 900)""",

            """ • Зарплаты выше €4 000–€4 200 (или $5 000) без опыта и квалификации — это практически невозможно;
 • Если вам обещают значительно больше, это повод насторожиться и перепроверить источники.

💡 Вывод:
Любые необоснованные цифры зарплаты — это один из явных признаков мошенничества.

<b>1️⃣3️⃣Проверка документов должна сопровождаться официальным отчётом.</b>
Отчёт о проверке (на наличие ограничений и возможности получения визы) приходит на вашу электронную почту, а не просто "на словах" от менеджера.

<b>1️⃣4️⃣Без собеседования трудоустройства не бывает.</b>
Ни один менеджер и ни одна компания не могут согласовать вашу кандидатуру с работодателем без интервью, звонка или видеорезюме.
Если этого не требуют — это 100% мошенничество.""",

            """<b>1️⃣5️⃣Визу невозможно получить по почте.</b>
В международном праве не существует процедуры, при которой виза высылается почтой.
Если вам говорят, что "визу вышлют, а вы вклеите её сами" — это прямой обман.

<b>1️⃣6️⃣Как действуют мошенники.</b>
Они делают вид, что ведут активную работу 5–7 дней, а затем присылают "договор" или "контракт" и требуют первую оплату.
Это невозможно, поскольку любые документы (контракт, приглашение, спонсорский сертификат) оформляются только на основании подписанного договора между вами и компанией."""
        ],

        [
            """⸻

🔹 <b>Реальный процесс трудоустройства</b>

Ниже приведена официальная последовательность этапов, которая отражает, как действительно проходит законное оформление документов и трудоустройство за границей.

⸻

<b>Первый этап — подача документов на проверку</b>

Вы отправляете необходимые документы, которые включают:
 1. 📘 Скан-копию заграничного паспорта (все заполненные страницы).
 2. 📗 Скан-копию внутреннего паспорта (все заполненные страницы).
 3. 🧾 Справку о несудимости, выданную не ранее чем за 3 месяца.
 4. 💳 Выписку из банка, подтверждающую вашу финансовую состоятельность на сумму, равную стоимости услуг агентства или посредника.""",

            """После предоставления всех документов менеджер может зарегистрировать визовую анкету для проверки возможности получения визы.
Вы заполняете анкету, после чего документы направляются на проверку в визовый центр, иммиграционную службу или посольство.
Проверяется наличие ограничений, действительность паспорта и возможность получения визы.
Результаты проверки поступают вам на электронную почту в виде официального отчёта.

⸻

<b>Второй этап — собеседование с работодателем</b>

В зависимости от требований работодателя проводится одно из следующих:
 • видеорезюме,
 • аудиособеседование,
 • онлайн- или офлайн-интервью (в удобной форме для работодателя или кандидата).

Без прохождения этого этапа ваша кандидатура не может быть согласована с работодателем.
Только после собеседования работодатель принимает окончательное решение — одобрить кандидата или отклонить.""",

            """⸻

<b>Третий этап — оплата и заключение договора</b>

В случае одобрения кандидатуры начинается этап оплаты и заключения договора.
Добросовестные компании, как правило, разбивают оплату на несколько частей, чтобы клиент понимал, за что он платит и какие документы подготавливаются.

После первой оплаты на протяжении суток составляется и направляется договор.
Клиент подписывает его, сканирует и отправляет обратно менеджеру или компании.
Менеджер, в свою очередь, направляет этот договор работодателю.

На основании подписанного договора работодатель может приступать к подготовке
рабочего контракта, Job Letter или спонсорского сертификата — в зависимости от страны трудоустройства."""
        ],

        [
            """<b>Четвёртый этап — оформление контракта и приглашения</b>

Каждый работодатель оформляет эти документы индивидуально.
Процесс занимает от 3 до 10 дней, как правило — около недели.

Работодатель подготавливает контракт, регистрирует его на сайте труда (например, в Германии)
и направляет все документы менеджеру.

Менеджер обязан:
 • проверить корректность данных по должности, зарплате, компании и часам работы;
 • убедиться, что контракт действительно зарегистрирован на официальном сайте;
 • и только после этого передать его клиенту с подробным разъяснением условий.

После подтверждения клиентом условий может производиться вторая часть оплаты,
а далее — подача документов на визу.""",

            """⸻

<b>Пятый этап — подача документов на визу</b>

Работодатель подаёт документы на визу.
Процесс рассмотрения занимает индивидуальное время в зависимости от страны,
но обычно не превышает 7–10 дней.

Посольство рассматривает документы и передаёт информацию в страну, где находится клиент —
в визовый центр Германии или аккредитированные агентства, уполномоченные на приём и выдачу виз.

Например:
 • в Российской Федерации — в визовый центр Германии в России,
либо в аккредитированные агентства;
 • в Узбекистане — в визовый центр Германии в Узбекистане,
либо соответствующие аккредитированные агентства;
 • в Казахстане — в визовый центр Германии в Казахстане и его представительства.""",

            """После этого назначается очередь на биометрические процедуры:
 • сдача отпечатков пальцев,
 • сканирование сетчатки глаза (например, в Великобритании эта процедура обязательна),
 • вклеивание визы.

На протяжении до 10 дней визовый центр сообщает вам дату, время и место процедуры.
Информация направляется на почту или номер телефона, указанные в анкете.

⸻

<b>Шестой этап — вклеивание визы и сдача биометрии</b>

В назначенную дату вы приходите по указанному адресу заранее — за 30 минут.

При себе необходимо иметь:
 • заграничный паспорт,
 • внутренний паспорт,
 • фотографию 35×45 мм (если не была предоставлена ранее).

Дополнительные документы не требуются, так как они уже были переданы посольством в визовый центр.""",

            """Вы сдаёте биометрию, которая вносится в базу в течение примерно двух часов,
после чего вам вклеивают визу в заграничный паспорт.

⸻

<b>Седьмой этап — получение визы, выезд и прибытие к работодателю</b>

После получения визы вы связываетесь с вашим менеджером или компанией, сообщаете о результате.
Менеджер связывается с работодателем и согласовывает дату вашего прибытия,
чтобы подготовить место проживания и все организационные детали.

В назначенную дату вы вылетаете в страну трудоустройства.
По прилёту вас встречает менеджер или куратор, который:
 • сопровождает вас на подписание оригиналов договоров,
 • организует заселение,
 • и доставляет непосредственно к работодателю для оформления и начала работы.""",

            """⸻

<b>Заключение</b>

Вот так должен выглядеть реальный процесс подготовки документов и трудоустройства.
И никак по-другому.

Независимо от того, направляетесь ли вы в Евросоюз или любую другую страну,
процесс должен включать все описанные этапы — с проверками, собеседованиями, договорами и официальным оформлением.

❌ Любые схемы, где от вас требуют лишь фото паспорта или простую анкету без проверки,
— это прямое мошенничество.

💡 Помните: "получить визу не напрягаясь" невозможно.
Всё оформление требует вашего личного участия — в сборе документов,
в подписях, в прохождении проверок и собеседований.
Именно ваше присутствие подтверждает подлинность данных
и делает процесс законным, прозрачным и безопасным"""
        ]
    ]
    
    return scam_info[page_id] if page_id < len(scam_info) else scam_info[0]

def load_about_images():
    """Загружает список фотографий из папки about_images в правильном порядке"""
    import os
    import re
    images = []
    
    if os.path.exists("about_images"):
        for filename in os.listdir("about_images"):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                images.append(os.path.join("about_images", filename))
    
    def extract_number(filename):
        match = re.search(r'(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    return sorted(images, key=extract_number)

def get_about_text(page_id):
    """Возвращает текст для страницы 'О нас' по номеру"""
    about_texts = [
        "ℹ️ <b>О нас</b>\n\nВсё началось в 2011 году, когда два брата — Алан и Алекс — приехали в Германию в поисках легальных возможностей для работы и проживания.\n\nНа тот момент найти надёжную поддержку было крайне сложно — не существовало агентств, которые могли бы комплексно помочь и с документами, и с трудоустройством.",
        "ℹ️ <b>О нас</b>\n\nПройдя этот путь самостоятельно и столкнувшись со множеством трудностей, братья решили создать компанию, которая помогала бы другим людям избежать тех же ошибок и начать свой путь в Европе проще и безопаснее.",
        "ℹ️ <b>О нас</b>\n\nТак, в 2011 году было официально основано кадровое агентство, которое на тот момент насчитывало всего двух сотрудников — самих основателей, Алана и Алекса.",
        "ℹ️ <b>О нас</b>\n\nУже к 2013 году агентство значительно выросло и переросло в аутсорсинговую компанию с командой из семи человек и собственным центральным офисом, который успешно работает и по сей день.",
        "ℹ️ <b>О нас</b>\n\nС каждым годом компания набирала обороты.\nВ 2015 году был открыт ещё один офис в Республике Польша, а в 2017 году — новый офис в Германии, в городе Франкфурт-на-Майне.\n\nК этому времени команда превысила 30 сотрудников, а само агентство вошло в топ лучших аутсорсинговых компаний Европы.",
        "ℹ️ <b>О нас</b>\n\nВ 2019 году компания продолжила расширяться и открыла ещё один офис во Франции.\nНа тот момент команда уже насчитывала около 65 сотрудников, работающих в нескольких странах Европы.",
        "ℹ️ <b>О нас</b>\n\nСледующие два года — 2020 и 2021 — стали самыми сложными за всю историю компании.\nВ мире началась пандемия COVID-19, и большинство стран ограничили въезд иностранных граждан, что серьёзно повлияло на сферу трудоустройства.\nНесмотря на трудности, компания сохранила команду, процессы и доверие клиентов, продолжая помогать людям настолько, насколько это было возможно в тех условиях.",
        "ℹ️ <b>О нас</b>\n\nВ 2022 году компания вошла в состав Allangroup, что стало новым этапом развития.\nПосле слияния мы расширили штат, который на тот момент уже насчитывал около 100 человек, и укрепили международное присутствие.",
        "ℹ️ <b>О нас</b>\n\nВ начале 2023 года мы начали активно развивать сотрудничество с ведущими мировыми компаниями, среди которых:\nDHL Express, FedEx, Deutsche Post, Leon, Amazon.\nЭто стало подтверждением высокого уровня доверия к бренду и качества предоставляемых нами услуг.\n\nВ 2024 году компания расширила географию сотрудничества и заключила партнёрства с крупными европейскими работодателями, среди которых:\nTesco, Carrefour, Lidl Logistics, Aldi, DHL Express, FedEx, Deutsche Post, Leon, Amazon, Marriott Hotels Group, Accor, Hilton Hotels, UPS, IKEA Logistics.\nБлагодаря этому наши сотрудники получили возможность работать не только на складах и в логистике, но и в сфере обслуживания, гостиничного бизнеса и розничной торговли.",
        "ℹ️ <b>О нас</b>\n\nВ 2025 году компания вышла на рынок Англии по аутсорсингу, и на тот момент количество наших сотрудников достигло уже 300 человек.",
        "ℹ️ <b>О нас</b>\n\n<b>Наша миссия</b>\n\nНесмотря на рост компании, расширение географии и партнёрств, мы по-прежнему руководствуемся изначальной идеей, заложенной в 2011 году: предоставлять людям возможность легального трудоустройства, объединяя оформление визы и работу в одном процессе. Мы никогда не планировали и не предполагали, что наша компания достигнет таких масштабов, будет сотрудничать с таким количеством работодателей и помогать стольким людям. Главная причина нашего успеха — честность и порядочность. Мы не даём рекламу, не продвигаем себя искусственно — наша работа строится на доверии и «сарафанном радио», когда довольные клиенты рекомендуют нас другим. Всё, что мы делаем, строится на прозрачности, доверии и искреннем стремлении помогать людям."
    ]
    
    return about_texts[page_id] if page_id < len(about_texts) else about_texts[0]

def load_company_life_images():
    """Загружает все фотографии из папки in_comp"""
    images = []
    try:
        for i in range(1, 22):
            image_path = f"in_comp/{i}.jpg"
            if not os.path.exists(image_path):
                image_path = f"in_comp/{i}.JPG"
            if os.path.exists(image_path):
                images.append(image_path)
    except Exception as e:
        logger.error(f"Ошибка загрузки фото из in_comp: {e}")
    return images

def get_company_life_text(page_id):
    """Возвращает текст для страницы 'Из жизни компании' по номеру"""
    life_texts = [
        "🤝🏾 С гражданами Казахстана в Берлине в офисе",
        "🤝🏾 Встреча с гражданами России в офисе",
        "🤝🏾 Обсуждаем рабочие моменты с гражданами Казахстана",
        "🤝🏾 Граждане Узбекистана которые работают на складе DHL",
        "🤝🏾 С гражданами Таджикистана в офисе",
        "🤝🏾 Граждане Казахстана которые работают на складе FedEx",
        "🤝🏾 Гражданин Российской Федерации подписывает договор по приезду",
        "🤝🏾 Встреча руководителя компании с сотрудником из Казахстана на объекте DHL",
        "🤝🏾 Гражданин Таджикистана который работает на складе DHL",
        "🤝🏾 Менеджер Софи встречает граждан Турции с Аэропорта",
        "🤝🏾 С гражданами Узбекистана в офисе компании",
        "🤝🏾 Рабочие моменты на складе «Lidl» с гражданами Таджикистана",
        "🤝🏾 Менеджер с руководителем обсуждают вопросы в офисе в Берлине",
        "🤝🏾 Наш Менеджер Софья во время рабочего дня!",
        "🤝🏾 Наши менеджера с руководством в офисе!",
        "🤝🏾 Прекрасный момент был запечатлен в центре Берлина возле нашего авто",
        "🤝🏾 Наш менеджер Софи на рабочем месте",
        "🤝🏾 Менеджер Софи общается с гражданами Таджикистана на складе Amazon",
        "🤝🏾 Граждане Азербайджана в офисе с руководителем",
        "🤝🏾 Менеджер возле автомобиля компании",
        "🤝🏾 С гражданами Российской Федерации в Берлине"
    ]
    
    return life_texts[page_id] if page_id < len(life_texts) else ""

def get_company_life_menu(current_page, total_pages):
    """Возвращает меню навигации для 'Из жизни компании'"""
    keyboard = []
    
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"life_{current_page - 1}"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"life_{current_page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")])
    
    return InlineKeyboardMarkup(keyboard)

def load_contract_images():
    """Загружает все фотографии договоров из папки sample_doc"""
    images = []
    try:
        for i in range(1, 9):
            image_path = f"sample_doc/{i}.png"
            if os.path.exists(image_path):
                images.append(image_path)
    except Exception as e:
        logger.error(f"Ошибка загрузки фото из sample_doc: {e}")
    return images

def get_contract_menu(current_page, total_pages):
    """Возвращает меню навигации для договоров"""
    keyboard = []
    
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"contract_{current_page - 1}"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Далее", callback_data=f"contract_{current_page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")])
    
    return InlineKeyboardMarkup(keyboard)

def get_manager_text(language):
    """Возвращает текст менеджера по языку"""
    manager_texts = {
        "ru": """📩 <b>Русскоязычные менеджеры:</b>
💬 Софи — @sophie_becker_work
💬 Алан — @allan_kai

📌 Пожалуйста, перед тем как писать, ознакомьтесь со всеми разделами бота.
Менеджеры отвечают только по рабочим вопросам, анкетам и трудоустройству.
Вопросы, ответы на которые есть в разделе «Вакансии», «Документы», «Гарантии» и т.д., не рассматриваются""",
        
        "en": """🇬🇧 <b>English-speaking manager:</b>
💬 Sophie — @sophie_becker_work

📌 Before messaging, please check all sections of the bot.
Managers reply only regarding job applications, recruitment, and work-related questions.
Questions already answered in the sections "Vacancies", "Documents", "Guarantees", etc. will not be reviewed.""",
        
        "de": """🇩🇪 <b>Deutschsprachiger Manager:</b>
💬 Sonia — @Abramova_works

📌 Bevor Sie eine Nachricht schreiben, lesen Sie bitte alle Abschnitte des Bots.
Manager beantworten nur Fragen zu Bewerbungen, Arbeit und Beschäftigung.
Fragen, die bereits in den Bereichen „Stellenangebote", „Dokumente", „Garantien" usw. beantwortet werden, werden nicht bearbeitet.""",
        
        "pl": """🇵🇱 <b>Menedżer mówiący po polsku:</b>
💬 Tomasz — @Wisniewski_tom

📌 Zanim napiszesz wiadomość, zapoznaj się ze wszystkimi sekcjami bota.
Menedżerowie odpowiadają tylko w sprawach związanych z rekrutacją, ankietami i zatrudnieniem.
Pytania, na które odpowiedzi znajdują się w sekcjach „Oferty pracy", „Dokumenty", „Gwarancje" itp., nie będą rozpatrywane.""",
        
        "fr": """🇫🇷 <b>Manager francophone:</b>
💬 Hayes — @hayes_will

📌 Avant d'écrire un message, veuillez consulter toutes les sections du bot.
Les managers répondent uniquement aux questions concernant les candidatures, le recrutement et l'emploi.
Les questions dont les réponses se trouvent déjà dans les sections « Offres d'emploi », « Documents », « Garanties », etc., ne seront pas traitées."""
    }
    
    return manager_texts.get(language, manager_texts["ru"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name or "пользователь"
    
    # Додаємо користувача в таблицю при старті
    add_user_to_sheet(user_id)
    
    args = context.args
    
    # Якщо є параметр visa - одразу починаємо візову анкету
    if args and args[0] == "visa":
        user_id = user.id
        
        # Перевіряємо, чи вже заповнював користувач форму
        if check_user_filled_visa(user_id):
            final_message = f"""🟢 <b>Уведомление о регистрации заявки</b>

✅ Ваша заявка успешно зарегистрирована в системе.
Регистрационный номер: {user_id}

Ваши документы переданы на стадию перевода и дальнейшей проверки
и будут направлены в:
 • визовый центр,
 • консульский отдел посольства,
 • иммиграционную службу — для проверки возможности получения данного типа визы по указанным вами данным.

⏳ Обработка может занять от 1 до 3 рабочих дней.
📩 Извещение о результатах вы получите на ваш e-mail указанный в анкете выше,
в виде официального письма.

⚠️ Важно: сообщите свой регистрационный номер менеджеру для подтверждения подачи и продолжения оформления документов."""
            
            await update.message.reply_text(final_message, reply_markup=get_main_menu(), parse_mode='HTML', protect_content=True)
            return
        
        visa_welcome_text = """📄 Добро пожаловать в систему предварительного заполнения визовой анкеты.

Анкета используется для оформления рабочей визы в выбранную страну.
Все сведения обрабатываются только уполномоченными специалистами для проверки документов к подаче в консульство."""
        
        keyboard = [
            [InlineKeyboardButton("✅ Да, начать", callback_data="start_visa_form")]
        ]
        
        await update.message.reply_text(
            visa_welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            protect_content=True
        )
        return
    
    if not args:
        welcome_text = f"""👋 <b>Приветствуем вас, {user_name}!</b>

Мы помогаем людям находить официальную работу за границей — честно, прозрачно и с полной поддержкой на каждом шаге.

Главное для нас — ваша безопасность и уверенность.
Мы понимаем, как непросто решиться на работу в другой стране, поэтому делаем всё,
чтобы этот путь был спокойным и понятным.

Мы не сотрудничаем с посредниками,
дабы снизить дополнительные расходы соискателей
и гарантировать только проверенных работодателей нашей компанией.

<b>Почему выбирают нас:</b>
• Официальное оформление
• Проверенные работодатели
• Поддержка до выезда, во время подготовки документов,
после приезда и весь срок контракта и вашей работы

👇 Выберите вакансию в меню ниже"""
    
    else:
        referral_code = args[0]
        
        if referral_code == "alan":
            manager_name = "Алана Кайзера"
        elif referral_code == "sofia_beker":
            manager_name = "Софи Бекер"
        elif referral_code == "sofia_abramova":
            manager_name = "Софии Абрамовой"
        else:
            manager_name = None
        
        if manager_name is None:
            welcome_text = f"""👋 <b>Приветствуем вас, {user_name}!</b>

Мы помогаем людям находить официальную работу за границей — честно, прозрачно и с полной поддержкой на каждом шаге.

Главное для нас — ваша безопасность и уверенность.
Мы понимаем, как непросто решиться на работу в другой стране, поэтому делаем всё,
чтобы этот путь был спокойным и понятным.

Мы не сотрудничаем с посредниками,
дабы снизить дополнительные расходы соискателей
и гарантировать только проверенных работодателей нашей компанией.

<b>Почему выбирают нас:</b>
• Официальное оформление
• Проверенные работодатели
• Поддержка до выезда, во время подготовки документов,
после приезда и весь срок контракта и вашей работы

👇 Выберите вакансию в меню ниже"""
        else:
            welcome_text = f"""👋👋 <b>Здравствуйте, {user_name}!</b>

Вы перешли по рекомендации нашего менеджера {manager_name}.

Вас приветствует Центр трудоустройства

Главное для нас — ваша безопасность и уверенность.
Мы понимаем, как непросто решиться на работу в другой стране, поэтому сделаем всё, чтобы этот путь был спокойным и понятным для Вас.

Мы работаем напрямую, без посредников.
Так вы не переплачиваете, а мы можем гарантировать, что все работодатели — надежные и проверенные нашей компанией.

👇 Выберите интересующую вакансию в меню ниже"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu(),
        parse_mode='HTML'
    ,
            protect_content=True
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await check_subscription(context.bot, user_id):
        await send_subscription_message(update, context)
        return
    
    text = update.message.text
    
    if text == "🧾 Вакансии":
        await update.message.reply_text(
            "🧾 <b>Вакансии по странам</b>\n\nВыберите страну для просмотра доступных вакансий:",
            reply_markup=get_countries_menu(),
            parse_mode='HTML'
        ,
            protect_content=True
        )
    
    elif text == "✅ Гарантии":
        await update.message.reply_text(
            "✅ <b>Гарантии</b>\n\nВыберите раздел:",
            reply_markup=get_guarantees_menu(),
            parse_mode='HTML'
        ,
            protect_content=True
        )
    
    elif text == "⭐ Отзывы (старий обробник удалено)":
        reviews = load_reviews()
        logger.info(f"Загрузено {len(reviews)} отзывов")
        
        if reviews:
            logger.info("🎬 Попробуем загрузить первое видео...")
            working_review_id = None
            
            for i in range(len(reviews)):
                try:
                    review = reviews[i]
                    logger.info(f"🎬 Попытка загрузить отзыв {i+1} (ID: {review['id']}) по URL: {review['video']}")
                    
                    success = False
                    for attempt in range(2):
                        try:
                            if attempt == 0:
                                await update.message.reply_video(
                                    video=review['video'],
                                    caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                    reply_markup=get_reviews_menu(i, len(reviews)),
                                    parse_mode='HTML',
            protect_content=True
        )
                            else:
                                await update.message.reply_video(
                                    video=review['video'],
                                    caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                    reply_markup=get_reviews_menu(i, len(reviews)),
                                    parse_mode='HTML',
            protect_content=True
        )
                            
                            success = True
                            logger.info(f"✅ Успешно загружен отзыв {i+1} (попытка {attempt+1})")
                            break
                            
                        except Exception as e:
                            logger.warning(f"⚠️ Попытка {attempt+1} неудачна для отзыва {i+1}: {str(e)}")
                            if attempt < 1:
                                await asyncio.sleep(0.5)
                            continue
                    
                    if success:
                        working_review_id = i
                        break
                    else:
                        logger.error(f"❌ Все попытки неудачны для отзыва {i+1}")
                        continue
                        
                except Exception as e:
                    logger.error(f"❌ Критическая ошибка загрузки отзыва {i+1}: {str(e)}")
                    continue
            
            if working_review_id is None:
                logger.error("❌ Ни один отзыв не удалось загрузить")
                await update.message.reply_text(
                    "⭐ <b>Отзывы наших клиентов</b>\n\nНекоторые видео временно недоступны из-за технических ограничений Telegram. Спробуйте пізніше.",
                    reply_markup=get_main_menu(),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        else:
            logger.warning("⚠️ Список отзывов пуст")
            await update.message.reply_text(
                "⭐ <b>Отзывы наших клиентов</b>\n\nПока нет отзывов.",
                reply_markup=get_main_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif text == "💬 Связаться с менеджером":
        await update.message.reply_text(
            "🌐 <b>Выберите язык общения:</b>",
            reply_markup=get_manager_language_menu(),
            parse_mode='HTML'
        ,
            protect_content=True
        )
    
    elif text == "📄 Лицензия (старий обробник удалено)":
        try:
            license_text = """Мы ценим доверие наших клиентов. Все лицензии подтверждают, что наша деятельность полностью законна и регулируется официальными органами."""
            
            video_url = "https://jusffjefihe.b-cdn.net/IMG_3781.mp4"
            
            await update.message.reply_video(
                video=video_url,
                caption=license_text,
                parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки видео: {e}")
            await update.message.reply_text("❌ Ошибка загрузки видео", protect_content=True)
    
    
    elif text == "❓ Вопрос - ответ":
        qa_list = load_qa()
        if qa_list:
            qa = qa_list[0]
            qa_text = f"""
<b>Вопрос:</b> {qa['question']}

<b>Ответ:</b> {qa['answer']}

<i>Вопрос 1 из {len(qa_list)}</i>
            """
            await update.message.reply_text(
                qa_text,
                reply_markup=get_qa_menu(0),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        else:
            await update.message.reply_text(
                "❓ <b>Вопрос - ответ</b>\n\nИнформация будет добавлена.",
                reply_markup=get_main_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif text == "🔄 Как мы работаем":
        workflow_text = """❗️ <b>Менеджер не предоставляет информацию, которая уже есть в боте.</b>
Он выполняет консультативную функцию и помогает по вопросам, связанным с вашей заявкой.

📌 <b>Для получения информации используйте соответствующие разделы бота:</b>
• «Лицензия» — чтобы убедиться в наличии лицензии компании или менеджера.
• «Отзывы» — чтобы ознакомиться с отзывами других пользователей.
• «Процесс работы» — чтобы изучить, как происходит трудоустройство и подготовка документов.
• «Вопрос-ответ» — часто задаваемые вопросы, с которыми также обязательно ознакомьтесь.

✅ <b>Только после ознакомления со всей информацией выбирайте вакансию и подавайте заявку.</b>"""
        
        try:
            with open("voices_howwework/first_mess.ogg", 'rb') as voice_file:
                await update.message.reply_voice(
                    voice=voice_file,
                    caption=workflow_text,
                    reply_markup=get_workflow_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await update.message.reply_text(
                workflow_text,
                reply_markup=get_workflow_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif text == "ℹ️ О нас":
        try:
            with open("logo.jpg", 'rb') as logo:
                keyboard = [
                    [InlineKeyboardButton("📖 Наша история", callback_data="about_history")],
                    [InlineKeyboardButton("🏢 Наши представительства", callback_data="about_offices")]
                ]
                await update.message.reply_photo(
                    photo=logo,
                    caption="ℹ️ <b>О нас</b>\n\nВыберите раздел для получения подробной информации:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки logo: {str(e)}")
            keyboard = [
                [InlineKeyboardButton("📖 Наша история", callback_data="about_history")],
                [InlineKeyboardButton("🏢 Наши представительства", callback_data="about_offices")]
            ]
            await update.message.reply_text(
                "ℹ️ <b>О нас</b>\n\nВыберите раздел для получения подробной информации:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif text == "📍 Контакты":
        contacts_text = """📞 <b>Контакты</b>

<b>Юридический адрес:</b>
🇩🇪 Frankfurt am Main, Germany — Theodor-Heuss-Allee 112 (строение 3)

<b>Офисы:</b>
🇩🇪 Berlin, Germany — <a href="https://www.google.com/maps/search/International+Trade+Centre,+Berlin">International Trade Centre (10 этаж, правое крыло)</a>
🇩🇪 Frankfurt am Main, Germany — <a href="https://www.google.com/maps/search/Theodor-Heuss-Allee+112,+Frankfurt+am+Main">Theodor-Heuss-Allee 112 (строение 3)</a>
🇵🇱 Szczecin, Poland — <a href="https://www.google.com/maps/search/Baltic+Business+Park,+Szczecin">Baltic Business Park (весь 3-й этаж)</a>
🇫🇷 Paris, France — <a href="https://www.google.com/maps/search/3+Bis+Rue+Taylor,+Paris">3 Bis Rue Taylor (1-й этаж)</a>
🇬🇧 Manchester, UK — <a href="https://www.google.com/maps/search/Empress+Business+Centre,+Manchester">Empress Business Centre (2-й этаж)</a>

<b>Телефоны:</b>
📞 +4915213678601 — 
Многоканальный 
❗️Не проводится консультирование по вакансиям и вопросам трудоустройства.
Используется исключительно для сотрудничества, партнёрств и деловых запросов.


<b>Email:</b>
✉️ Alllangroup@web.de

Форма обратной связи / кнопка
— "💬 Написать менеджеру" """
        
        keyboard = [
            [InlineKeyboardButton("💬 Написать менеджеру", callback_data="manager_ru")]
        ]
        
        await update.message.reply_text(
            contacts_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        ,
            protect_content=True
        )
    
    elif text == "🛡️ Как не попасть на мошенников (старий обробник удалено)":
        messages = get_scam_info_text(0)
        
        for i, message_text in enumerate(messages):
            if i == len(messages) - 1:
                await update.message.reply_text(
                    message_text,
                    reply_markup=get_scam_info_menu(0),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
            else:
                await update.message.reply_text(
                    message_text,
                    parse_mode='HTML'
                ,
            protect_content=True
        )
    
    else:
        await update.message.reply_text(
            "Выберите нужный раздел из меню:",
            reply_markup=get_main_menu()
        ,
            protect_content=True
        )

async def form_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник первого вопроса - ПІБ"""
    text = update.message.text.strip()
    if is_main_menu_text(text):
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        await text_handler(update, context)
        return -1
    if not text:
        await update.message.reply_text(
            "1️⃣ <b>Фамилия, Имя, Отчество:</b>\n\nНапишите ответ ниже в чат 👇",
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return FORM_NAME
    
    context.user_data['form_name'] = text
    await update.message.reply_text(
        "2️⃣ <b>Дата рождения:</b>\n\nНапишите ответ ниже в чат 👇",
        parse_mode='HTML'
    ,
            protect_content=True
        ,
            reply_markup=get_main_menu()
        )
    return FORM_BIRTH_DATE

async def form_birth_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник другого вопроса - дата народження"""
    text = update.message.text.strip()
    if is_main_menu_text(text):
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        await text_handler(update, context)
        return -1
    if not text:
        await update.message.reply_text(
            "2️⃣ <b>Дата рождения:</b>\n\nНапишите ответ ниже в чат 👇",
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return FORM_BIRTH_DATE
    
    context.user_data['form_birth_date'] = text
    await update.message.reply_text(
        "3️⃣ <b>Гражданство:</b>\n\nНапишите ответ ниже в чат 👇",
        parse_mode='HTML'
    ,
            protect_content=True
        ,
            reply_markup=get_main_menu()
        )
    return FORM_CITIZENSHIP

async def form_citizenship_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник третього вопроса - громадянство"""
    text = update.message.text.strip()
    if is_main_menu_text(text):
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        await text_handler(update, context)
        return -1
    if not text:
        await update.message.reply_text(
            "3️⃣ <b>Гражданство:</b>\n\nНапишите ответ ниже в чат 👇",
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return FORM_CITIZENSHIP
    
    context.user_data['form_citizenship'] = text
    await update.message.reply_text(
        "4️⃣ <b>Где вы сейчас находитесь (страна / город):</b>\n\nНапишите ответ ниже в чат 👇",
        parse_mode='HTML'
    ,
            protect_content=True
        ,
            reply_markup=get_main_menu()
        )
    return FORM_LOCATION

async def form_location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник четвертого вопроса - місцезнаходження"""
    text = update.message.text.strip()
    if is_main_menu_text(text):
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        await text_handler(update, context)
        return -1
    if not text:
        await update.message.reply_text(
            "4️⃣ <b>Где вы сейчас находитесь (страна / город):</b>\n\nНапишите ответ ниже в чат 👇",
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return FORM_LOCATION
    
    context.user_data['form_location'] = text
    await update.message.reply_text(
        "5️⃣ <b>Контактный номер для связи:</b>\n(укажите WhatsApp / Telegram — где вам удобнее общаться)\n📱 Напишите ответ ниже в чат 👇",
        parse_mode='HTML'
    ,
            protect_content=True
        ,
            reply_markup=get_main_menu()
        )
    return FORM_CONTACT

async def form_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник п'ятого вопроса - контакт"""
    text = update.message.text.strip()
    if is_main_menu_text(text):
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        await text_handler(update, context)
        return -1
    if not text:
        await update.message.reply_text(
            "5️⃣ <b>Контактный номер для связи:</b>\n(укажите WhatsApp / Telegram — где вам удобнее общаться)\n📱 Напишите ответ ниже в чат 👇",
            parse_mode='HTML'
        ,
            protect_content=True
        )
        return FORM_CONTACT
    
    context.user_data['form_contact'] = text
    
    keyboard = [
        [InlineKeyboardButton("Для себя", callback_data="work_self")],
        [InlineKeyboardButton("С друзьями / родственниками", callback_data="work_friends")],
        [InlineKeyboardButton("Семейной парой", callback_data="work_couple")]
    ]
    await update.message.reply_text(
        "6️⃣ <b>Вы ищете работу:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    ,
            protect_content=True
        )
    return FORM_WORK_SEEKING

async def form_work_seeking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник шостого вопроса - що шукаєте"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["work_self", "work_friends", "work_couple"]:
            answers = {
                "work_self": "Для себя",
                "work_friends": "С друзьями / родственниками",
                "work_couple": "Семейной парой"
            }
            answer = answers[data]
            context.user_data['form_work_seeking'] = answer
            await update.callback_query.message.edit_text(
                f"6️⃣ <b>Вы ищете работу:</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="passport_yes")],
                [InlineKeyboardButton("В процессе оформления", callback_data="passport_process")],
                [InlineKeyboardButton("Нет", callback_data="passport_no")]
            ]
            await update.callback_query.message.reply_text(
                "7️⃣ <b>Есть ли у вас действующий загранпаспорт?</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_PASSPORT
    return FORM_WORK_SEEKING

async def form_passport_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник сьомого вопроса - паспорт"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["passport_yes", "passport_process", "passport_no"]:
            answers = {
                "passport_yes": "Да",
                "passport_process": "В процессе оформления",
                "passport_no": "Нет"
            }
            answer = answers[data]
            context.user_data['form_passport'] = answer
            await update.callback_query.message.edit_text(
                f"7️⃣ <b>Есть ли у вас действующий загранпаспорт?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="visa_yes")],
                [InlineKeyboardButton("Нет", callback_data="visa_no")]
            ]
            await update.callback_query.message.reply_text(
                "8️⃣ <b>Есть ли у вас готовые документы для выезда (виза)?</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_VISA_DOCS
    return FORM_PASSPORT

async def form_visa_docs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник восьмого вопроса - віза"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["visa_yes", "visa_no"]:
            answer = "Да" if data == "visa_yes" else "Нет"
            context.user_data['form_visa_docs'] = answer
            await update.callback_query.message.edit_text(
                f"8️⃣ <b>Есть ли у вас готовые документы для выезда (виза)?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Нет, всё было без проблем", callback_data="diff_no")],
                [InlineKeyboardButton("Да, были небольшие сложности", callback_data="diff_small")],
                [InlineKeyboardButton("Да, была депортация / отказ", callback_data="diff_deport")],
                [InlineKeyboardButton("Никогда за границей не работал", callback_data="diff_never")]
            ]
            await update.callback_query.message.reply_text(
                "9️⃣ <b>Были ли у вас когда-либо сложности при выезде или работе за границей?</b>\n(например, отказ в визе, депортация, нарушение визового режима и т. д.)",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_DIFFICULTIES
    return FORM_VISA_DOCS

async def form_difficulties_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник дев'ятого вопроса - складності"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["diff_no", "diff_small", "diff_deport", "diff_never"]:
            answers = {
                "diff_no": "Нет, всё было без проблем",
                "diff_small": "Да, были небольшие сложности",
                "diff_deport": "Да, была депортация / отказ",
                "diff_never": "Никогда за границей не работал"
            }
            answer = answers[data]
            context.user_data['form_difficulties'] = answer
            await update.callback_query.message.edit_text(
                f"9️⃣ <b>Были ли у вас когда-либо сложности?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Сразу же (3–7 дней)", callback_data="speed_now")],
                [InlineKeyboardButton("Позже (2–4 недели)", callback_data="speed_later")],
                [InlineKeyboardButton("Пока не определился", callback_data="speed_unsure")]
            ]
            await update.callback_query.message.reply_text(
                "🔟 <b>При одобрении анкеты, насколько быстро вы готовы начать оформление?</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_READY_SPEED
    return FORM_DIFFICULTIES

async def form_ready_speed_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник десятого вопроса - готовність"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["speed_now", "speed_later", "speed_unsure"]:
            answers = {
                "speed_now": "Сразу же (3–7 дней)",
                "speed_later": "Позже (2–4 недели)",
                "speed_unsure": "Пока не определился"
            }
            answer = answers[data]
            context.user_data['form_ready_speed'] = answer
            await update.callback_query.message.edit_text(
                f"🔟 <b>Насколько быстро вы готовы начать оформление?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="money_yes")],
                [InlineKeyboardButton("Будет возможность в ближайшее время", callback_data="money_soon")],
                [InlineKeyboardButton("Пока нет", callback_data="money_no")]
            ]
            await update.callback_query.message.reply_text(
                "1️⃣1️⃣ <b>Есть ли у вас сейчас возможность покрыть базовые расходы на оформление?</b>\n(визовые платежи, консульские и сервисные сборы, переводы документов, базовые организационные сборы)",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_FINANCIAL_ABILITY
    return FORM_READY_SPEED

async def form_financial_ability_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник одинадцятого вопроса - фінанси"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["money_yes", "money_soon", "money_no"]:
            answers = {
                "money_yes": "Да",
                "money_soon": "Будет возможность в ближайшее время",
                "money_no": "Пока нет"
            }
            answer = answers[data]
            context.user_data['form_financial_ability'] = answer
            await update.callback_query.message.edit_text(
                f"1️⃣1️⃣ <b>Есть ли у вас возможность покрыть расходы?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("Да", callback_data="ready_yes")],
                [InlineKeyboardButton("Нужно немного времени", callback_data="ready_need_time")],
                [InlineKeyboardButton("Пока не уверен", callback_data="ready_unsure")]
            ]
            await update.callback_query.message.reply_text(
                "1️⃣2️⃣ <b>Если всё подойдёт по условиям, готовы ли вы сразу перейти к оформлению документов?</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_IMMEDIATE_START
    return FORM_FINANCIAL_ABILITY

async def form_immediate_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник дванадцятого вопроса - готовність одразу"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["ready_yes", "ready_need_time", "ready_unsure"]:
            answers = {
                "ready_yes": "Да",
                "ready_need_time": "Нужно немного времени",
                "ready_unsure": "Пока не уверен"
            }
            answer = answers[data]
            context.user_data['form_immediate_start'] = answer
            await update.callback_query.message.edit_text(
                f"1️⃣2️⃣ <b>Готовы ли вы сразу перейти к оформлению документов?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            keyboard = [
                [InlineKeyboardButton("На 6 месяцев", callback_data="term_6")],
                [InlineKeyboardButton("На 1 год", callback_data="term_12")],
                [InlineKeyboardButton("Другой срок (указать)", callback_data="term_other")]
            ]
            await update.callback_query.message.reply_text(
                "1️⃣3️⃣ <b>На какой срок вы планируете оформить визу?</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
            return FORM_VISA_TERM
    return FORM_IMMEDIATE_START

async def form_visa_term_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник тринадцятого вопроса - термін візи"""
    if update.callback_query:
        data = update.callback_query.data
        if data in ["term_6", "term_12"]:
            answers = {
                "term_6": "На 6 месяцев",
                "term_12": "На 1 год"
            }
            answer = answers[data]
            context.user_data['form_visa_term'] = answer
            await update.callback_query.message.edit_text(
                f"1️⃣3️⃣ <b>На какой срок вы планируете оформить визу?</b>\n\n<b>Ответ:</b> {answer}",
                parse_mode='HTML'
            )
            
            user_id = update.callback_query.from_user.id
            form_data = {
                'user_id': user_id,
                'name': context.user_data.get('form_name', ''),
                'birth_date': context.user_data.get('form_birth_date', ''),
                'citizenship': context.user_data.get('form_citizenship', ''),
                'location': context.user_data.get('form_location', ''),
                'contact': context.user_data.get('form_contact', ''),
                'work_seeking': context.user_data.get('form_work_seeking', ''),
                'passport': context.user_data.get('form_passport', ''),
                'visa_docs': context.user_data.get('form_visa_docs', ''),
                'difficulties': context.user_data.get('form_difficulties', ''),
                'ready_speed': context.user_data.get('form_ready_speed', ''),
                'financial_ability': context.user_data.get('form_financial_ability', ''),
                'immediate_start': context.user_data.get('form_immediate_start', ''),
                'visa_term': context.user_data.get('form_visa_term', ''),
                'vacancy_title': context.user_data.get('form_vacancy_title', '')
            }
            
            save_success = save_to_sheets(form_data)
            
            channel_success = await send_to_channel(context, form_data)
            
            submitted_applications.add(user_id)
            
            for key in list(context.user_data.keys()):
                if key.startswith('form_') or key.startswith('waiting_'):
                    del context.user_data[key]
            
            if save_success or channel_success:
                await update.callback_query.message.reply_text(
                    "✅ <b>Ваша заявка успешно зарегистрирована в системе</b>",
                    reply_markup=get_main_menu(),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
            else:
                await update.callback_query.message.reply_text(
                    "❌ <b>Ошибка отправки заявки</b>\n\n"
                    "Попробуйте позже или обратитесь к менеджеру.",
                    reply_markup=get_main_menu(),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
            return -1
        elif data == "term_other":
            await update.callback_query.message.edit_text(
                "1️⃣3️⃣ <b>На какой срок вы планируете оформить визу?</b>\n\n<b>Ответ:</b> Другой срок",
                parse_mode='HTML'
            )
            await update.callback_query.message.reply_text(
                "Напишите свой срок ниже 👇",
                parse_mode='HTML'
            ,
            protect_content=True
        ,
                reply_markup=get_main_menu()
        )
            context.user_data['waiting_for_term_text'] = True
            return FORM_VISA_TERM
        
    elif update.message and context.user_data.get('waiting_for_term_text', False):
        text = update.message.text.strip()
        if is_main_menu_text(text):
            for key in list(context.user_data.keys()):
                if key.startswith('form_') or key.startswith('waiting_'):
                    del context.user_data[key]
            await text_handler(update, context)
            return -1
        context.user_data['form_visa_term'] = text
        
        user_id = update.message.from_user.id
        form_data = {
            'user_id': user_id,
            'name': context.user_data.get('form_name', ''),
            'birth_date': context.user_data.get('form_birth_date', ''),
            'citizenship': context.user_data.get('form_citizenship', ''),
            'location': context.user_data.get('form_location', ''),
            'contact': context.user_data.get('form_contact', ''),
            'work_seeking': context.user_data.get('form_work_seeking', ''),
            'passport': context.user_data.get('form_passport', ''),
            'visa_docs': context.user_data.get('form_visa_docs', ''),
            'difficulties': context.user_data.get('form_difficulties', ''),
            'ready_speed': context.user_data.get('form_ready_speed', ''),
            'financial_ability': context.user_data.get('form_financial_ability', ''),
            'immediate_start': context.user_data.get('form_immediate_start', ''),
            'visa_term': context.user_data.get('form_visa_term', ''),
            'vacancy_title': context.user_data.get('form_vacancy_title', '')
        }
        
        save_success = save_to_sheets(form_data)
        
        channel_success = await send_to_channel(context, form_data)
        
        submitted_applications.add(user_id)
        
        for key in list(context.user_data.keys()):
            if key.startswith('form_') or key.startswith('waiting_'):
                del context.user_data[key]
        
        if save_success or channel_success:
            await update.message.reply_text(
                "✅ <b>Ваша заявка успешно зарегистрирована в системе</b>",
                reply_markup=get_main_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        else:
            await update.message.reply_text(
                "❌ <b>Ошибка отправки заявки</b>\n\n"
                "Попробуйте позже или обратитесь к менеджеру.",
                reply_markup=get_main_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        return -1
    return FORM_VISA_TERM

async def cancel_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена формы"""
    for key in list(context.user_data.keys()):
        if key.startswith('form_') or key.startswith('waiting_'):
            del context.user_data[key]
    
    await update.message.reply_text(
        "❌ Заполнение анкеты отменено.",
        reply_markup=get_main_menu(),
        parse_mode='HTML'
    ,
            protect_content=True
        )
    return -1

async def start_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало формы предварительной анкеты"""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        
        if user_id in submitted_applications:
            await query.answer("❌ Вы уже заполнили предварительную анкету!", show_alert=True)
            return -1
        
        if check_user_submitted(user_id):
            submitted_applications.add(user_id)
            await query.answer("❌ Вы уже заполнили предварительную анкету!", show_alert=True)
            return -1
        
        await query.answer()

        # Скрываем главное меню на время заполнения формы (приховуємо без окремого повідомлення)
        
        parts = query.data.split("_")
        country_code = parts[1]
        vacancy_id = int(parts[2])
        
        vacancies = load_vacancies(country_code)
        vacancy = next((v for v in vacancies if v["id"] == vacancy_id), None)
        
        if not vacancy:
            await safe_edit_message(query, "❌ Вакансия не найдена")
            return -1
        
        context.user_data['form_vacancy'] = vacancy
        context.user_data['form_vacancy_title'] = vacancy['title']
        
        # Відправляємо нове повідомлення замість редагування, щоб попереднє з вакансією не видалялось
        # Приховуємо меню при цьому
        await query.message.reply_text(
            "📝 <b>Предварительная анкета</b>\n\n"
            "Пожалуйста, заполните все поля.\n"
            "⚠️ Если пропустите хотя бы одно поле, заявка не будет передана менеджеру.\n\n"
            "1️⃣ <b>Фамилия, Имя, Отчество:</b>\n\nНапишите ответ ниже в чат 👇",
            parse_mode='HTML',
            reply_markup=get_main_menu()
        )
        
        return FORM_NAME
    
    return -1

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Виключаємо перевірку підписки для кнопки нагадувань
    if query.data != "check_subscription" and query.data != "notification_show_vacancies" and not await check_subscription(context.bot, user_id):
        subscription_text = f"""🔥 <b>Лучшие вакансии — только для подписчиков!</b>

Мы публикуем самые свежие и выгодные предложения работы в канале Центр Трудоустройства | раньше, чем где-либо ещё.

<b>Подпишитесь сейчас, чтобы не пропустить шанс на отличную работу!</b>

После подписки нажмите «✅ Я подписался» и продолжайте."""
        
        keyboard = [
            [InlineKeyboardButton("📢 Перейти до каналу", url=f"https://t.me/+xG5QAaLGbT03NDky")],
            [InlineKeyboardButton("✅ Я підписався", callback_data="check_subscription")]
        ]
        
        await query.edit_message_text(
            subscription_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return
    
    data = query.data
    
    # Обробник для кнопки в нагадувальних повідомленнях
    if data == "notification_show_vacancies":
        await query.answer()
        chat_id = query.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text="🧾 <b>Вакансии по странам</b>\n\nВыберите страну для просмотра доступных вакансий:",
            reply_markup=get_countries_menu(),
            parse_mode='HTML',
            protect_content=True
        )
        return
    
    if data == "countries":
        chat_id = query.message.chat_id
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="🧾 <b>Вакансии по странам</b>\n\nВыберите страну для просмотра доступных вакансий:",
            reply_markup=get_countries_menu(),
            parse_mode='HTML',
            protect_content=True
        )
    
    elif data.startswith("country_"):
        country_code = data.split("_")[1]
        country_name = COUNTRIES[country_code]["name"]
        vacancies = load_vacancies(country_code)
        chat_id = query.message.chat_id
        
        if vacancies:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧾 <b>Вакансии в {country_name}</b>\n\nВыберите вакансию для просмотра деталей:",
                reply_markup=get_country_vacancies_menu(country_code),
                parse_mode='HTML',
            protect_content=True
        )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧾 <b>Вакансии в {country_name}</b>\n\nПока нет доступных вакансий для этой страны.",
                reply_markup=get_country_vacancies_menu(country_code),
                parse_mode='HTML',
            protect_content=True
        )
    
    elif data.startswith("vacancy_"):
        parts = data.split("_")
        country_code = parts[1]
        vacancy_id = int(parts[2])
        
        vacancies = load_vacancies(country_code)
        vacancy = next((v for v in vacancies if v["id"] == vacancy_id), None)
        
        if vacancy:
            keyboard = [
                [InlineKeyboardButton("📝 Оставить заявку", callback_data=f"apply_{country_code}_{vacancy_id}")],
                [InlineKeyboardButton("🔙 Назад к вакансиям", callback_data=f"country_{country_code}")]
            ]
            
            full_text = f"{vacancy['title']}\n\n{vacancy['description']}"
            
            MAX_LENGTH = 1024 if vacancy.get('image') else 4096
            
            if vacancy.get('image'):
                image_path = vacancy['image']
                try:
                    if len(full_text) <= MAX_LENGTH:
                        chat_id = query.message.chat_id
                        
                        with open(image_path, 'rb') as photo_file:
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_file,
                                caption=full_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='HTML',
            protect_content=True
                            )
                    else:
                        chat_id = query.message.chat_id
                        
                        with open(image_path, 'rb') as photo_file:
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_file,
                                caption=f"{vacancy['title']}",
                                parse_mode='HTML',
                                protect_content=True
                            )
                        
                        remaining_text = vacancy['description']
                        MAX_TEXT_LENGTH = 4096
                        
                        while remaining_text:
                            if len(remaining_text) <= MAX_TEXT_LENGTH:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=remaining_text,
                                    reply_markup=InlineKeyboardMarkup(keyboard),
                                    parse_mode='HTML'
                                ,
            protect_content=True
        )
                                remaining_text = ""
                            else:
                                chunk = remaining_text[:MAX_TEXT_LENGTH]
                                last_newline = chunk.rfind('\n')
                                if last_newline > MAX_TEXT_LENGTH - 200:
                                    chunk = chunk[:last_newline]
                                
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=chunk + "\n\n<i>... продолжение ниже ...</i>",
                                    parse_mode='HTML'
                                ,
            protect_content=True
        )
                                remaining_text = remaining_text[len(chunk):]
                except FileNotFoundError:
                    logger.error(f"Файл изображения не найден: {image_path}")
                    if len(full_text) <= 4096:
                        await query.edit_message_text(
                            full_text,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='HTML'
                        )
            else:
                if len(full_text) <= MAX_LENGTH:
                    await query.edit_message_text(
                        full_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    )
                else:
                    first_part = full_text[:MAX_LENGTH]
                    last_newline = first_part.rfind('\n')
                    if last_newline > MAX_LENGTH - 200:
                        first_part = first_part[:last_newline]
                    
                    await query.edit_message_text(
                        first_part + "\n\n<i>... продолжение ниже ...</i>",
                        parse_mode='HTML'
                    )
                    
                    remaining_text = full_text[len(first_part):]
                    chat_id = query.message.chat_id
                    
                    while remaining_text:
                        if len(remaining_text) <= MAX_LENGTH:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=remaining_text,
                                reply_markup=InlineKeyboardMarkup(keyboard),
                                parse_mode='HTML'
                            ,
            protect_content=True
        )
                            remaining_text = ""
                        else:
                            chunk = remaining_text[:MAX_LENGTH]
                            last_newline = chunk.rfind('\n')
                            if last_newline > MAX_LENGTH - 200:
                                chunk = chunk[:last_newline]
                            
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=chunk + "\n\n<i>... продолжение ниже ...</i>",
                                parse_mode='HTML'
                            ,
            protect_content=True
        )
                            remaining_text = remaining_text[len(chunk):]
        else:
            await query.edit_message_text(
                "❌ Вакансия не найдена",
                parse_mode='HTML'
            )
    
    elif data == "reviews":
        reviews = load_reviews()
        logger.info(f"🔄 Обработка кнопки reviews: загружено {len(reviews)} отзывов")
        
        if reviews:
            logger.info("🔍 Проверяем доступность всех видео...")
            available_reviews = []
            for i, review in enumerate(reviews):
                is_available = await check_video_availability(review['video'])
                if is_available:
                    available_reviews.append((i, review))
                else:
                    logger.warning(f"⚠️ Видео {i+1} (ID: {review['id']}) недоступно: {review['video']}")
            
            logger.info(f"📊 Доступно {len(available_reviews)} из {len(reviews)} видео")
            
            if available_reviews:
                working_review_id = None
                for i, review in available_reviews:
                    try:
                        logger.info(f"🎬 Попытка загрузить отзыв {i+1} (ID: {review['id']}) по URL: {review['video']}")
                        await query.message.reply_video(
                            video=review['video'],
                            caption=f"⭐ <b>Отзывы наших клиентов</b>",
                            reply_markup=get_reviews_menu(i, len(reviews)),
                            parse_mode='HTML',
            protect_content=True
        )
                        working_review_id = i
                        logger.info(f"✅ Успешно загружен отзыв {i+1}")
                        break
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки отзыва {i+1}: {str(e)}")
                        continue
                
                if working_review_id is None:
                    logger.error("❌ Ни один отзыв не удалось загрузить")
                    await query.message.reply_text(
                        f"⭐ <b>Отзывы наших клиентов</b>\n\nВсе видео временно недоступны.",
                        parse_mode='HTML'
                    ,
            protect_content=True
        )
            else:
                logger.error("❌ Ни одно видео не доступно")
                await query.message.reply_text(
                    f"⭐ <b>Отзывы наших клиентов</b>\n\nВсе видео временно недоступны.",
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        else:
            logger.warning("⚠️ Список отзывов пуст")
            await query.edit_message_text(
                "⭐ <b>Отзывы наших клиентов</b>\n\nПока нет отзывов.",
                parse_mode='HTML'
            )
    
    elif data == "guarantees_visas":
        visas = load_visas()
        if visas:
            visa = visas[0]
            chat_id = query.message.chat_id
            
            with open(visa['image'], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    reply_markup=get_visas_menu(0),
                    parse_mode='HTML',
            protect_content=True
        )
        else:
            await query.message.delete()

            await query.reply_text(
                "📋 <b>Визы</b>\n\nИнформация о визах будет добавлена.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")]]),
                parse_mode='HTML'
            )
    
    elif data == "guarantees_certificates":
        certificates = load_certificates()
        if certificates:
            certificate = certificates[0]
            chat_id = query.message.chat_id
            
            with open(certificate['image'], 'rb') as photo_file:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file,
                    reply_markup=get_certificates_menu(0),
                    parse_mode='HTML',
            protect_content=True
        )
        else:
            await query.message.delete()

            await query.reply_text(
                "📜 <b>Сертификаты</b>\n\nИнформация о сертификатах будет добавлена.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")]]),
                parse_mode='HTML'
            )
    
    elif data == "guarantees_legality":
        legality_text = """
⚖️ <b>ПРАВОВОЙ СТАТУС ДЕЯТЕЛЬНОСТИ</b>

Наша компания ведёт деятельность в сфере международного трудоустройства в строгом соответствии с нормами национального и международного права, включая законодательство Федеративной Республики Германия, а также нормативные акты Европейского Союза, регулирующие трудовую и миграционную политику.

Мы официально зарегистрированы на портале Федерального агентства по труду Германии (Bundesagentur für Arbeit) — центрального государственного органа, контролирующего легальность посреднических услуг и соблюдение стандартов занятости иностранных граждан.
Регистрация на данном портале подтверждает, что наша деятельность прошла проверку компетентными органами Германии и соответствует установленным требованиям к компаниям, имеющим право на международное трудоустройство.

Наша работа основана на официальных договорах и разрешениях, выданных уполномоченными структурами Германии и стран-партнёров.
Все процедуры по подбору персонала, оформлению визовых и трудовых документов проходят в соответствии с положениями миграционного и трудового законодательства.

Каждый кандидат получает:
• Официальный трудовой договор от работодателя;
• Контрактовую и визовую поддержку;
• Документальное подтверждение законности трудоустройства.

Мы не используем теневых схем, не взимаем скрытых комиссий и не сотрудничаем с посредниками.
Все финансовые операции осуществляются прозрачно, с предоставлением договоров, чеков и квитанций.

Мы придерживаемся принципов законности, прозрачности и защиты прав соискателей.
Каждого кандидата сопровождаем от первичной консультации до официального выхода на работу, обеспечивая полное соблюдение всех юридических требований.

📄 <b>Наши гарантии включают:</b>
• Официальную регистрацию в органах занятости Германии;
• Действующие международные договоры и партнёрские соглашения;
• Полное юридическое сопровождение и защиту интересов кандидатов;
• Абсолютную прозрачность всех документов и финансовых операций.

Мы осознаём ответственность перед каждым соискателем и работаем на основании принципов законности, открытости и доверия, что делает нас надёжным, официально признанным партнёром в вопросах международного трудоустройства.

⚖️ <b>ОФИЦИАЛЬНАЯ РЕГИСТРАЦИЯ:</b>
Зарегистрированы на портале Bundesagentur für Arbeit — Федерального агентства по труду Германии.
Деятельность компании подтверждена и регулируется трудовым и миграционным законодательством Германии.
Работаем исключительно по официальным контрактам, без посредников и скрытых схем.

📁 Посмотреть подтверждающие документы вы можете на главном экране или в главном меню во вкладке «Документы».
        """
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")]]
        await query.edit_message_text(
            legality_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    elif data == "guarantees_back":
        chat_id = query.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ <b>Гарантии</b>\n\nВыберите раздел:",
            reply_markup=get_guarantees_menu(),
            parse_mode='HTML',
            protect_content=True
        )
    
    elif data.startswith("certificate_"):
        certificate_id = int(data.split("_")[1])
        certificates = load_certificates()
        
        if certificate_id < 0:
            certificate_id = len(certificates) - 1
        elif certificate_id >= len(certificates):
            certificate_id = 0
        
        if certificates:
            certificate = certificates[certificate_id]
            
            with open(certificate['image'], 'rb') as photo_file:
                await query.edit_message_media(
                    media=telegram.InputMediaPhoto(
                        media=photo_file
                    ),
                    reply_markup=get_certificates_menu(certificate_id)
                )
    
    elif data.startswith("visa_"):
        visa_id = int(data.split("_")[1])
        visas = load_visas()
        
        if visa_id < 0:
            visa_id = len(visas) - 1
        elif visa_id >= len(visas):
            visa_id = 0
        
        if visas:
            visa = visas[visa_id]
            
            with open(visa['image'], 'rb') as photo_file:
                await query.edit_message_media(
                    media=telegram.InputMediaPhoto(
                        media=photo_file
                    ),
                    reply_markup=get_visas_menu(visa_id)
                )
    
    elif data.startswith("review_"):
        review_id = int(data.split("_")[1])
        reviews = load_reviews()
        
        logger.info(f"🔄 Обработка кнопки отзыва: review_id={review_id}, всего отзывов={len(reviews)}")
        
        if review_id < 0:
            review_id = len(reviews) - 1
            logger.info(f"⬅️ Отзыв ID меньше 0, установлено на {review_id}")
        elif review_id >= len(reviews):
            review_id = 0
            logger.info(f"➡️ Отзыв ID больше максимального, установлено на {review_id}")
        
        if reviews:
            try:
                await query.message.delete()
                logger.info("🗑️ Старое сообщение с отзывом удалено")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить старое сообщение: {str(e)}")
            
            current_review = reviews[review_id]
            
            try:
                logger.info(f"🎬 Загрузка отзыва {review_id+1} (ID: {current_review['id']}) по URL: {current_review['video']}")
                
                success = False
                for attempt in range(2):
                    try:
                        if attempt == 0:
                            await context.bot.send_video(
                                chat_id=query.message.chat_id,
                                video=current_review['video'],
                                caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                reply_markup=get_reviews_menu(review_id, len(reviews)),
                                parse_mode='HTML',
            protect_content=True
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=query.message.chat_id,
                                video=current_review['video'],
                                caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                reply_markup=get_reviews_menu(review_id, len(reviews)),
                                parse_mode='HTML',
            protect_content=True
                            )
                        
                        success = True
                        logger.info(f"✅ Успешно загружен отзыв {review_id+1} (попытка {attempt+1})")
                        break
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Попытка {attempt+1} неудачна для отзыва {review_id+1}: {str(e)}")
                        if attempt < 1:
                            await asyncio.sleep(0.5)
                        continue
                
                if not success:
                    logger.error(f"❌ Все попытки неудачны для отзыва {review_id+1}")
                    await find_next_available_review(context, query, review_id, reviews)
                    
            except Exception as e:
                logger.error(f"❌ Критическая ошибка загрузки отзыва {review_id+1}: {str(e)}")
                await find_next_available_review(context, query, review_id, reviews)
        else:
            logger.warning("⚠️ Список отзывов пуст")
            await query.edit_message_text(
                "⭐ <b>Отзывы наших клиентов</b>\n\nПока нет отзывов.",
                parse_mode='HTML'
            )
    
    elif data.startswith("qa_"):
        qa_id = int(data.split("_")[1])
        qa_list = load_qa()
        
        if qa_id < 0:
            qa_id = len(qa_list) - 1
        elif qa_id >= len(qa_list):
            qa_id = 0
        
        if qa_list:
            qa = qa_list[qa_id]
            qa_text = f"""
<b>Вопрос:</b> {qa['question']}

<b>Ответ:</b> {qa['answer']}

<i>Вопрос {qa_id + 1} из {len(qa_list)}</i>
            """
            await query.edit_message_text(
                qa_text,
                reply_markup=get_qa_menu(qa_id),
                parse_mode='HTML'
            )
    
    
    
    elif data == "documents":
        documents_text = """
📄 <b>Наши документы и лицензии</b>

✅ <b>Документы, подтверждающие нашу деятельность:</b>

• 📋 Лицензия на предоставление услуг по трудоустройству
• 📜 Сертификат качества ISO 9001:2015
• 🤝 Договоры с работодателями Европы
• 📊 Статистика успешных трудоустройств
• 🏆 Награды и отличия

📹 <b>Видео о нашей работе:</b>
• Экскурсия по офису
• Интервью с сотрудниками
• Процесс оформления документов

🔗 <b>Полезные ссылки:</b>
• Регистрация в Министерстве труда
• Справка из Единого госреестра
• Отзывы на официальных сайтах

<i>Все документы можно просмотреть в нашем офисе или по запросу.</i>
        """
        
        await query.edit_message_text(
            documents_text,
            parse_mode='HTML'
        )
    
    
    elif data == "workflow":
        workflow_text = """
ℹ️ <b>Как мы работаем</b>

🔄 <b>Этапы трудоустройства:</b>

<b>1️⃣ Подача заявки</b>
• Заполнение анкеты
• Предоставление контактных данных
• Выбор вакансии

<b>2️⃣ Звонок менеджера</b>
• Консультация по вакансии
• Уточнение деталей
• Ответы на вопросы

<b>3️⃣ Подготовка документов</b>
• Помощь с оформлением
• Проверка документов
• Подготовка к собеседованию

<b>4️⃣ Собеседование с работодателем</b>
• Онлайн или телефонное собеседование
• Проверка квалификации
• Обсуждение условий

<b>5️⃣ Подписание договоров</b>
• Трудовой договор
• Договор с нашей компанией
• Медицинский осмотр

<b>6️⃣ Выезд и начало работы</b>
• Организация переезда
• Встреча в стране работы
• Начало трудовой деятельности

⏱️ <b>Сроки:</b> 2-4 недели от подачи заявки до выезда

💰 <b>Стоимость услуг:</b> Бесплатно для работника
        """
        
        await query.edit_message_text(
            workflow_text,
            parse_mode='HTML'
        )
    
    elif data == "workflow_documents":
        documents_text = """📄 <b>Документы, необходимые для трудоустройства</b>

1. Скан копия заграничного паспорта — все заполненные страницы.
2. Скан копия внутреннего паспорта — все заполненные страницы.
3. Справка о несудимости — действующая и официально заверенная.
4. Выписка с банка — подтверждает вашу финансовую состоятельность на сумму, указанную в вакансии.
⚠️ Может быть предоставлена позже, при подаче анкеты работодателю.
5. Две фотографии формата 35×45 мм — можно прикрепить позже при подаче документов на визу, если сейчас их нет.

💬 <b>Важно:</b> если по выбранной вакансии потребуются дополнительные документы, менеджер обязательно озвучит это при телефонном звонке."""
        
        await query.message.delete()
        
        try:
            with open("voices_howwework/documents.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=documents_text,
                    reply_markup=get_documents_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                documents_text,
                reply_markup=get_documents_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_first_stage":
        first_stage_text = """1️⃣ <b>Первый этап — выбор вакансии и подача заявки</b>

1. 🔍 <b>Выбираете вакансию</b>
• Перейдите во вкладку «Вакансии» и выберите подходящую позицию.
• Обратите внимание на требования к языкам и условия предоставления жилья (если указано).

2. 📝 <b>Заполнение заявки</b>
• Нажмите «Оставить заявку».
• Заполните все поля анкеты.
⚠️ Если пропустите хоть одно поле, заявка не будет передана менеджеру.
• Нажмите «Отправить».

3. ⏱ <b>Ожидание связи</b>
• В течение суток (иногда чуть дольше из-за большого количества заявок) с вами свяжется менеджер.
• Важно: указывайте актуальные номера для WhatsApp и Telegram — менеджер связывается через эти приложения.

4. 📞 <b>Дальнейшая связь и собеседование с менеджером</b>
• Менеджер перезвонит и проведёт краткое собеседование, задаст все вопросы компании.
• При необходимости зарегистрирует вас на сайте посольства для заполнения визовой анкеты.
• Вы заполняете анкету, менеджер переводит её на немецкий язык, чтобы перейти к следующему этапу — проверке документов."""
        
        try:
            with open("voices_howwework/1.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=first_stage_text,
                    reply_markup=get_first_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                first_stage_text,
                reply_markup=get_first_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_second_stage":
        second_stage_text = """2️⃣ <b>Второй этап — проверка документов</b>

1. ⏳ <b>Ожидание проверки</b>
• Проверяются ваши документы на наличие ограничений или запретов на выезд.
• Определяется, выдадут ли вам данный тип визы.
• Процедура занимает обычно около суток.

2. 📧 <b>Получение отчёта</b>
• Результаты приходят на ваш e-mail в виде официального документа.
⚠️ Указывайте верный адрес электронной почты, чтобы не пропустить информацию.

3. 👩‍💼 <b>Дальнейшие действия</b>
• Вы отправляете отчёт менеджеру.
• Менеджер изучает его и сообщает, можно ли переходить к следующему этапу — рассмотрению кандидатуры работодателем, собеседованию или видеорезюме."""
        
        try:
            with open("voices_howwework/2.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=second_stage_text,
                    reply_markup=get_second_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                second_stage_text,
                reply_markup=get_second_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_third_stage":
        third_stage_text = """3️⃣ <b>Третий этап — рассмотрение кандидатуры работодателем</b>

1. 🎯 <b>Собеседование или видеорезюме</b>
• В зависимости от требований работодателя на выбранную вакансию менеджер сообщит вам, в каком формате будет проводиться отбор:
• Аудио- или видеособеседование, либо
• Видеорезюме.

2. 📅 <b>Организация и сроки</b>
• Работодатель проводит собеседование и в течение одного рабочего дня, не считая дня проведения собеседования, сообщает результаты менеджеру:
• принимает вас как соискателя, либо
• отклоняет вашу кандидатуру.

3. ✅ <b>Положительный ответ работодателя</b>
• Если работодатель готов взять вас на рабочее место, он делает соответствующие отметки на сайте посольства, подтверждая, что вы приняты и можно готовить договор.
• Менеджер связывается с вами и уведомляет о положительном ответе, после чего вы переходите к следующему этапу трудоустройства.

4. ⚠️ <b>Важно:</b>
• Без прохождения этого этапа ваша кандидатура не может быть согласована или рассмотрена работодателем."""
        
        try:
            with open("voices_howwework/3.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=third_stage_text,
                    reply_markup=get_third_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                third_stage_text,
                reply_markup=get_third_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_fourth_stage":
        fourth_stage_text = """4️⃣ <b>Четвёртый этап — первая оплата и подготовка договора</b>

1. 💰 <b>Первая оплата</b>
• После того как менеджер подтвердил, что работодатель сделал соответствующую отметку о принятии вас, вносится половина от стоимости услуги.
• Примеры:
• Полугодовая виза: 550 € → первая оплата 275 €
• Годовая виза: 750 € → первая оплата 375 €
• Менеджер регистрирует заявку на оплату, вы делаете перевод и отправляете квитанцию.

2. 📝 <b>Подготовка договора</b>
• На протяжении суток после оплаты менеджер составляет договор.
• Договор подписывает директор компании и отправляется вам для подписи.
• Вы распечатываете договор, ставите подписи и отправляете обратно менеджеру.

3. 📤 <b>Отправка работодателю</b>
• Менеджер направляет подписанный договор работодателю, чтобы он мог начать подготовку:
• Рабочего контракта,
• Job letter, либо
• Приглашения/спонсорского сертификата (в зависимости от страны)."""
        
        try:
            with open("voices_howwework/4.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=fourth_stage_text,
                    reply_markup=get_fourth_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                fourth_stage_text,
                reply_markup=get_fourth_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_fifth_stage":
        fifth_stage_text = """5️⃣ <b>Пятый этап — получение и проверка рабочего контракта</b>

1. 📄 <b>Подготовка контракта</b>
• После того как менеджер отправил подписанный вами договор, работодатель в течение 3–5 рабочих дней готовит рабочий контракт.

2. ✅ <b>Проверка менеджером</b>
• Менеджер принимает контракт и проверяет:
• регистрацию на сайте труда страны трудоустройства,
• соответствие всех условий, согласованных ранее с вами:
• зарплата,
• место работы,
• часы работы,
• остальные условия труда.

3. 📤 <b>Отправка и ознакомление</b>
• Контракт отправляется вам для ознакомления.
• Менеджер набирает вас по телефону и подробно рассказывает о всех условиях.
• Вы сверяете информацию и можете задать все интересующие вопросы, на которые менеджер отвечает.

4. 💰 <b>Вторая оплата и отправка документов</b>
• По окончании разговора менеджер регистрирует заявку на оплату оставшейся половины суммы.
• Вы оплачиваете и отправляете квитанцию менеджеру для подтверждения.
• После второй оплаты на следующий день документы отправляются в посольство для одобрения визы."""
        
        try:
            with open("voices_howwework/5.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=fifth_stage_text,
                    reply_markup=get_fifth_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                fifth_stage_text,
                reply_markup=get_fifth_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_sixth_stage":
        sixth_stage_text = """6️⃣ <b>Шестой этап — подача документов работодателем на визу</b>

1. 📤 <b>Отправка документов</b>
• После второй оплаты работодатель подает документы на визу в посольство.

2. 🕒 <b>Процесс рассмотрения</b>
• В течение одной недели посольство:
• обрабатывает документы,
• принимает решение о выдаче визы,
• передает всю необходимую информацию и документы в визовый центр вашей страны.

3. 🏢 <b>Обработка визовым центром</b>
• Визовый центр принимает документы и ориентируется на срок контракта и дату вашего первого рабочего дня.
• Формирует запись для сдачи биометрии (отпечатки пальцев и/или скан сетчатки глаз, если требуется) и вклеивания визы.

4. 📧📱 <b>Уведомление</b>
• Информация о дате, времени и месте сдачи биометрии приходит вам на:
• электронную почту, или
• СМС-уведомление на мобильный телефон,
• в зависимости от страны, в которой вы находитесь.

✅ <b>Важно:</b> сдача биометрии и получение визы производится только лично вами, без участия посредников или менеджеров."""
        
        try:
            with open("voices_howwework/6.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=sixth_stage_text,
                    reply_markup=get_sixth_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                sixth_stage_text,
                reply_markup=get_sixth_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_seventh_stage":
        seventh_stage_text = """7️⃣ <b>Седьмой этап — сдача биометрии и получение визы</b>

1. 🕒 <b>Прибытие в визовый центр</b>
• В указанную дату и время приходите за 30 минут до назначенного времени.
• При себе необходимо иметь:
• заграничный паспорт,
• внутренний паспорт.

2. 🖐 <b>Сдача биометрии</b>
• Сдаёте отпечатки пальцев (и/или скан сетчатки глаз, если требуется).
• Процедура внесения данных в базу занимает около 2 часов, ожидайте это время.

3. 📌 <b>Вклеивание визы</b>
• После завершения биометрии вам вклеивают визу.

4. 📞 <b>Уведомление менеджера</b>
• После получения визы свяжитесь с менеджером и уведомьте о факте получения."""
        
        try:
            with open("voices_howwework/7.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=seventh_stage_text,
                    reply_markup=get_seventh_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                seventh_stage_text,
                reply_markup=get_seventh_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_eighth_stage":
        eighth_stage_text = """8️⃣ <b>Восьмой этап — согласование даты прибытия и назначение куратора</b>

1. 📞 <b>Связь с работодателем</b>
• Менеджер связывается с работодателем и согласовывает дату вашего прибытия.

2. 🏠 <b>Проживание и организация прибытия</b>
• Обсуждаются детали:
• где вы будете проживать,
• куда вас заселят,
• назначение первого рабочего дня.

3. 👤 <b>Назначение куратора</b>
• Вам назначается куратор, который будет встречать на рабочем месте.
• Вам передаются контактные номера куратора, а куратору передаются ваши контакты для связи."""
        
        try:
            with open("voices_howwework/8.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=eighth_stage_text,
                    reply_markup=get_eighth_stage_menu(),
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                eighth_stage_text,
                reply_markup=get_eighth_stage_menu(),
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data == "workflow_ninth_stage":
        ninth_stage_text = """9️⃣ <b>Девятый этап — прибытие в страну и начало работы</b>

1. ✈️ <b>Прибытие на территорию страны</b>
• Вы прибываете в страну, куда направляетесь для трудоустройства.

2. 👤 <b>Встреча с куратором</b>
• В аэропорту вас встречает куратор.
• У него будет на листе формата A4 ваше имя и фамилия для идентификации.

3. 🏠 <b>Заселение и оформление документов</b>
• Куратор сопровождает вас до места проживания.
• Подписываются необходимые документы для трудоустройства.

4. 💼 <b>Связь с работодателем и начало работы</b>
• Устанавливается контакт с работодателем.
• После этого вы приступаете к обучению и работе согласно выбранной вакансии.

✅ <b>Важно:</b> куратор обеспечивает сопровождение и организацию всех процессов до момента, когда вы полностью начинаете работу."""
        
        try:
            with open("voices_howwework/9.ogg", 'rb') as voice_file:
                await query.message.reply_voice(
                    voice=voice_file,
                    caption=ninth_stage_text,
                    parse_mode='HTML',
            protect_content=True
        )
        except Exception as e:
            logger.error(f"Ошибка отправки голосового сообщения: {str(e)}")
            await query.message.reply_text(
                ninth_stage_text,
                parse_mode='HTML'
            ,
            protect_content=True
        )
    
    elif data.startswith("guarantees_"):
        if data == "guarantees_back":
            await query.edit_message_text(
                "✅ <b>Гарантии</b>\n\nВыберите раздел:",
                reply_markup=get_guarantees_menu(),
                parse_mode='HTML'
            )
        elif data == "guarantees_reviews":
            reviews = load_reviews()
            logger.info(f"Загрузено {len(reviews)} отзывов")
            
            if reviews:
                logger.info("🎬 Попробуем загрузить первое видео...")
                working_review_id = None
                
                for i in range(len(reviews)):
                    try:
                        review = reviews[i]
                        logger.info(f"🎬 Попытка загрузить отзыв {i+1} (ID: {review['id']}) по URL: {review['video']}")
                        
                        success = False
                        for attempt in range(2):
                            try:
                                if attempt == 0:
                                    await query.message.reply_video(
                                        video=review['video'],
                                        caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                        reply_markup=get_reviews_menu(i, len(reviews)),
                                        parse_mode='HTML',
            protect_content=True
        )
                                else:
                                    await query.message.reply_video(
                                        video=review['video'],
                                        caption=f"⭐ <b>Отзывы наших клиентов</b>",
                                        reply_markup=get_reviews_menu(i, len(reviews)),
                                        parse_mode='HTML',
            protect_content=True
        )
                                
                                success = True
                                logger.info(f"✅ Успешно загружен отзыв {i+1} (попытка {attempt+1})")
                                break
                                
                            except Exception as e:
                                logger.warning(f"⚠️ Попытка {attempt+1} неудачна для отзыва {i+1}: {str(e)}")
                                if attempt < 1:
                                    await asyncio.sleep(0.5)
                                continue
                        
                        if success:
                            working_review_id = i
                            break
                        else:
                            logger.error(f"❌ Ошибка загрузки отзыва {i+1}: Все попытки неудачны")
                            continue
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки отзыва {i+1}: {str(e)}")
                        continue
                
                if working_review_id is None:
                    logger.error("❌ Не удалось загрузить ни одного отзыва")
                    keyboard = [
                        [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
                    ]
                    await query.message.reply_text(
                        "⭐ <b>Отзывы наших клиентов</b>\n\nВсе видео временно недоступны.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML'
                    ,
            protect_content=True
        )
            else:
                logger.error("❌ Не удалось загрузить список отзывов")
                keyboard = [
                    [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
                ]
                await query.message.reply_text(
                    "⭐ <b>Отзывы наших клиентов</b>\n\nВсе видео временно недоступны.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        
        elif data == "guarantees_scam":
            intro_text = (
                "⚠️ <b>Важно! Ознакомьтесь перед подачей документов</b>\n\n"
                "Чтобы не попасться на мошенников и понимать, как на самом деле выглядит процесс официального трудоустройства за границей, внимательно ознакомьтесь с приведённой ниже информацией."
            )
            keyboard = [
                [InlineKeyboardButton("🔎 Подробнее", callback_data="scam_0")]
            ]
            await query.message.reply_text(
                intro_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        
        elif data == "guarantees_visas":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
            ]
            await query.message.reply_text(
                "📋 <b>Визы клиентов</b>\n\nИнформация будет добавлена.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        
        elif data == "guarantees_certificates":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
            ]
            await query.message.reply_text(
                "📜 <b>Сертификаты клиентов</b>\n\nИнформация будет добавлена.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        
        elif data == "guarantees_legality":
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
            ]
            await query.message.reply_text(
                "⚖️ <b>Законность</b>\n\nИнформация будет добавлена.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        
        elif data == "guarantees_license":
            try:
                license_text = """Мы ценим доверие наших клиентов. Все лицензии подтверждают, что наша деятельность полностью законна и регулируется официальными органами."""
                
                video_url = "https://jusffjefihe.b-cdn.net/IMG_3781.mp4"
                
                keyboard = [
                    [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
                ]
                
                await query.message.reply_video(
                    video=video_url,
                    caption=license_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
            except Exception as e:
                logger.error(f"Ошибка отправки видео: {e}")
                keyboard = [
                    [InlineKeyboardButton("🔙 Назад к гарантиям", callback_data="guarantees_back")]
                ]
                await query.message.reply_text(
                    "❌ Ошибка загрузки видео",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                ,
            protect_content=True
        )
        
        elif data == "guarantees_privacy":
            privacy_text = """🛡️ <b>Политика конфиденциальности</b>

Мы ценим вашу доверие и гарантируем полную защиту личных данных.

<b>1. Сбор данных</b>
Бот может запрашивать минимальные данные — имя, номер телефона, страну проживания и другую информацию, необходимую для связи и подбора вакансий.

<b>2. Использование данных</b>
Вся полученная информация используется только для связи с вами, консультирования и предоставления услуг по трудоустройству.

<b>3. Передача данных третьим лицам</b>
Мы не передаём, не продаём и не распространяем ваши данные третьим лицам. Исключение возможно только по вашему письменному согласию или по требованию закона.

<b>4. Хранение данных</b>
Информация хранится в защищённой системе и может быть удалена по вашему запросу в любое время.

<b>5. Удаление или изменение данных</b>
Для удаления или изменения информации напишите менеджеру или на почту 📩 support@web.de

<b>6. Согласие</b>
Используя бот, вы подтверждаете согласие с данной политикой."""

            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="guarantees_back")]
            ]
            
            await query.message.reply_text(
                privacy_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        
        elif data == "guarantees_life":
            images = load_company_life_images()
            
            if images:
                try:
                    with open(images[0], 'rb') as photo:
                        await query.message.reply_photo(
                            photo=photo,
                            caption=get_company_life_text(0),
                            reply_markup=get_company_life_menu(0, len(images)),
                            parse_mode='HTML',
            protect_content=True
        )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {str(e)}")
                    await query.message.reply_text(
                        get_company_life_text(0),
                        reply_markup=get_company_life_menu(0, len(images)),
                        parse_mode='HTML'
                    ,
            protect_content=True
        )
            else:
                await query.message.reply_text(
                    get_company_life_text(0),
                    reply_markup=get_company_life_menu(0, 1),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        
        elif data == "guarantees_contract":
            images = load_contract_images()
            
            if images:
                try:
                    caption = f"📝 Образец договора ({1}/{len(images)})"
                    with open(images[0], 'rb') as photo:
                        await query.message.reply_photo(
                            photo=photo,
                            caption=caption,
                            reply_markup=get_contract_menu(0, len(images)),
                            parse_mode='HTML',
            protect_content=True
        )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото договору: {str(e)}")
                    await query.message.reply_text(
                        "📝 Образец договора",
                        reply_markup=get_contract_menu(0, len(images)),
                        parse_mode='HTML'
                    ,
            protect_content=True
        )
            else:
                await query.message.reply_text(
                    "📝 Образец договора\n\nФото временно недоступны.",
                    reply_markup=get_contract_menu(0, 1),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
    
    elif data.startswith("manager_"):
        if data == "manager_back":
            await query.edit_message_text(
                "🌐 <b>Выберите язык общения:</b>",
                reply_markup=get_manager_language_menu(),
                parse_mode='HTML'
            )
        else:
            language = data.split("_")[1]
            manager_text = get_manager_text(language)
            
            await query.edit_message_text(
                manager_text,
                reply_markup=get_manager_back_menu(),
                parse_mode='HTML'
            )
    
    elif data.startswith("about_"):
        if data == "about_history":
            images = load_about_images()
            
            if images:
                try:
                    with open(images[0], 'rb') as photo:
                        await query.message.reply_photo(
                            photo=photo,
                            caption=get_about_text(0),
                            reply_markup=get_about_menu(0, len(images)),
                            parse_mode='HTML',
            protect_content=True
        )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {str(e)}")
                    await query.message.reply_text(
                        get_about_text(0),
                        reply_markup=get_about_menu(0, len(images)),
                        parse_mode='HTML'
                    ,
            protect_content=True
        )
            else:
                await query.message.reply_text(
                    get_about_text(0),
                    reply_markup=get_about_menu(0, 1),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "about_offices":
            await query.message.delete()
            
            offices_text = "🏢 <b>Наши представительства</b>\n\nВыберите офис для получения подробной информации:"
            
            keyboard = [
                [InlineKeyboardButton("🇩🇪 Frankfurt am Main, Germany", callback_data="about_office_frankfurt")],
                [InlineKeyboardButton("🇩🇪 Berlin, Germany", callback_data="about_office_berlin")],
                [InlineKeyboardButton("🇵🇱 Szczecin, Poland", callback_data="about_office_szczecin")],
                [InlineKeyboardButton("🇫🇷 Paris, France", callback_data="about_office_paris")],
                [InlineKeyboardButton("🇬🇧 Manchester, UK", callback_data="about_office_manchester")]
            ]
            
            await query.message.reply_text(
                offices_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            ,
            protect_content=True
        )
        elif data == "about_back":
            await query.edit_message_text(
                "Выберите нужный раздел из меню:",
                reply_markup=get_main_menu()
            )
        elif data == "about_office_frankfurt":
            await query.message.delete()
            
            office_text = """🇩🇪 <b>Frankfurt am Main, Germany</b>

Theodor-Heuss-Allee 112 (строение 3)
👉 <a href="https://www.google.com/maps/search/Theodor-Heuss-Allee+112,+60486+Frankfurt+am+Main">Открыть на карте</a>"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к представительствам", callback_data="about_offices")]
            ]
            
            with open("ofices/1.jpg", 'rb') as photo_file:
                await query.message.reply_photo(
                    photo=photo_file,
                    caption=office_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        elif data == "about_office_berlin":
            await query.message.delete()
            
            office_text = """🇩🇪 <b>Berlin, Germany</b>

International Trade Centre (10 этаж, правое крыло)
👉 <a href="https://www.google.com/maps/search/International+Trade+Centre,+Berlin">Открыть на карте</a>"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к представительствам", callback_data="about_offices")]
            ]
            
            with open("ofices/2.jpg", 'rb') as photo_file:
                await query.message.reply_photo(
                    photo=photo_file,
                    caption=office_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        elif data == "about_office_szczecin":
            await query.message.delete()
            
            office_text = """🇵🇱 <b>Szczecin, Poland</b>

Baltic Business Park (весь 3-й этаж)
👉 <a href="https://www.google.com/maps/search/Baltic+Business+Park,+Szczecin">Открыть на карте</a>"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к представительствам", callback_data="about_offices")]
            ]
            
            with open("ofices/3.jpg", 'rb') as photo_file:
                await query.message.reply_photo(
                    photo=photo_file,
                    caption=office_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        elif data == "about_office_paris":
            await query.message.delete()
            
            office_text = """🇫🇷 <b>Paris, France</b>

3 Bis Rue Taylor (1-й этаж)
👉 <a href="https://www.google.com/maps/search/3+Bis+Rue+Taylor,+Paris">Открыть на карте</a>"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к представительствам", callback_data="about_offices")]
            ]
            
            with open("ofices/4.jpg", 'rb') as photo_file:
                await query.message.reply_photo(
                    photo=photo_file,
                    caption=office_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        elif data == "about_office_manchester":
            await query.message.delete()
            
            office_text = """🇬🇧 <b>Manchester, UK</b>

Empress Business Centre (2-й этаж)
👉 <a href="https://www.google.com/maps/search/Empress+Business+Centre,+Manchester">Открыть на карте</a>"""
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к представительствам", callback_data="about_offices")]
            ]
            
            with open("ofices/5.jpg", 'rb') as photo_file:
                await query.message.reply_photo(
                    photo=photo_file,
                    caption=office_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
            protect_content=True
        )
        else:
            await handle_about_navigation(query, context, data)
    
    elif data.startswith("life_"):
        page_id = int(data.split("_")[1])
        images = load_company_life_images()
        
        if images and page_id < len(images):
            try:
                with open(images[page_id], 'rb') as photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(
                            media=photo,
                            caption=get_company_life_text(page_id),
                            parse_mode='HTML'
                        ),
                        reply_markup=get_company_life_menu(page_id, len(images))
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки фото: {str(e)}")
                await query.message.delete()

                await query.reply_text(
                    get_company_life_text(page_id),
                    reply_markup=get_company_life_menu(page_id, len(images)),
                    parse_mode='HTML'
                )
    
    elif data.startswith("contract_"):
        page_id = int(data.split("_")[1])
        images = load_contract_images()
        
        if images and page_id < len(images):
            try:
                caption = f"📝 Образец договора ({page_id + 1}/{len(images)})"
                with open(images[page_id], 'rb') as photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(
                            media=photo,
                            caption=caption,
                            parse_mode='HTML'
                        ),
                        reply_markup=get_contract_menu(page_id, len(images))
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки фото договору: {str(e)}")
                await query.message.delete()

                await query.reply_text(
                    f"📝 Образец договора ({page_id + 1}/{len(images)})",
                    reply_markup=get_contract_menu(page_id, len(images)),
                    parse_mode='HTML'
                )
    
    elif data.startswith("scam_"):
        if data == "scam_0":
            await query.message.delete()
            
            scam_text = """<b>Основные признаки мошенничества</b>

1️⃣ Трудоустройство невозможно только по фото загранпаспорта!"""
            
            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_1")]
            ]
            
            try:
                with open("voives_scams/1.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/1.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_1":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "2️⃣Недостоверные или завышенные обещания!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_2")]
            ]

            try:
                with open("voives_scams/2.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/2.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_2":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "3️⃣Поддельные лицензии в электронном формате!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_3")]
            ]

            try:
                with open("voives_scams/3.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/3.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_3":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "4️⃣Отсутствие реального офиса и подтверждения деятельности!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_4")]
            ]

            try:
                with open("voives_scams/4.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/4.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_4":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "5️⃣ Гарантии 100% трудоустройства!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_5")]
            ]

            try:
                with open("voives_scams/5.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/5.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_5":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "6️⃣ Обещания трёхразового питания за счет работодателя!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_6")]
            ]

            try:
                with open("voives_scams/6.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/6.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_6":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "7️⃣ Показ договоров, контрактов или приглашений через исчезающие сообщения!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_7")]
            ]

            try:
                with open("voives_scams/7.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/7.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_7":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "8️⃣ Виза выдается только после сдачи биометрии и лично соискателю!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_8")]
            ]

            try:
                with open("voives_scams/8.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/8.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_8":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "9️⃣ Отсутствие англоязычных кураторов или менеджеров"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_9")]
            ]

            try:
                with open("voives_scams/9.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/9.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_9":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "🔟 Видео с места работы и «демонстрация менеджера»"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_10")]
            ]

            try:
                with open("voives_scams/10.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/10.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_10":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣1️⃣ Наличие лицензии у посредника или менеджера по трудоустройству!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_11")]
            ]

            try:
                with open("voives_scams/11.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/11.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_11":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣2️⃣ Завышение зарплат - признак мошенничества"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_12")]
            ]

            try:
                with open("voives_scams/12.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/12.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_12":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣3️⃣ Проверка документов должна сопровождаться официальным отчётом."
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_13")]
            ]

            try:
                with open("voives_scams/13.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/13.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_13":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣4️⃣ Без собеседования трудоустройства не бывает!"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_14")]
            ]

            try:
                with open("voives_scams/14.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/14.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_14":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣5️⃣ Визу невозможно получить по почте и как действуют мошенники."
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_15")]
            ]

            try:
                with open("voives_scams/15.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/15.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_15":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣6️⃣ Признаки мошенничества: давление и эмоциональные манипуляции."
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_16")]
            ]

            try:
                with open("voives_scams/16.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/16.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_16":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣7️⃣ Изменение условий оплаты"
            )

            keyboard = [
                [InlineKeyboardButton("➡️ Далее", callback_data="scam_17")]
            ]

            try:
                with open("voives_scams/17.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/17.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_17":
            await query.message.delete()
            
            scam_text = (
                "<b>Основные признаки мошенничества</b>\n\n"
                "1️⃣8️⃣ Схема «одного единственного платежа» - как работают мошенники."
            )

            keyboard = [
                [InlineKeyboardButton("Реальный процесс трудоустройства ✅", callback_data="scam_18")]
            ]

            try:
                with open("voives_scams/18.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/18.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        elif data == "scam_18":
            await query.message.delete()
            
            scam_text = "✅ Поведение профессиональных компаний"

            try:
                with open("voives_scams/real.ogg", 'rb') as voice_file:
                    await context.bot.send_voice(
                        chat_id=query.message.chat_id,
                        voice=voice_file,
                        caption=scam_text,
                        parse_mode='HTML',
            protect_content=True
        )
            except FileNotFoundError:
                logger.error("Голосовой файл не найден: voives_scams/real.ogg")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=scam_text,
                    parse_mode='HTML'
                ,
            protect_content=True
        )
        else:
            await handle_scam_navigation(query, context, data)
    
    elif data == "check_subscription":
        user_id = query.from_user.id
        
        if await check_subscription(context.bot, user_id):
            await query.edit_message_text(
                "✅ <b>Спасибо за подписку!</b>\n\nТеперь вы можете пользоваться всеми функциями бота.",
                reply_markup=get_main_menu(),
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ Вы еще не подписались на канал. Пожалуйста, подпишитесь и попробуйте снова.", show_alert=True)


async def handle_about_navigation(query, context, data):
    page_id = int(data.split("_")[1])
    images = load_about_images()
    
    if images and page_id < len(images):
        try:
            with open(images[page_id], 'rb') as photo:
                await query.message.reply_photo(
                    photo=photo,
                    caption=get_about_text(page_id),
                    reply_markup=get_about_menu(page_id, len(images)),
                    parse_mode='HTML',
            protect_content=True
        )
                await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка отправки фото {page_id}: {str(e)}")
            await query.edit_message_text(
                get_about_text(page_id),
                reply_markup=get_about_menu(page_id, len(images)),
                parse_mode='HTML'
            )
    else:
        await query.edit_message_text(
            get_about_text(page_id),
            reply_markup=get_about_menu(page_id, max(len(images), 1)),
            parse_mode='HTML'
        )


async def handle_scam_navigation(query, context, data):
    if data == "scam_back":
        await query.edit_message_text(
            "Выберите нужный раздел из меню:",
            reply_markup=get_main_menu()
        )
    else:
        page_id = int(data.split("_")[1])
        messages = get_scam_info_text(page_id)

        for i, message_text in enumerate(messages):
            if i == len(messages) - 1:
                await query.message.reply_text(
                    message_text,
                    reply_markup=get_scam_info_menu(page_id),
                    parse_mode='HTML'
                ,
            protect_content=True
        )
            else:
                await query.message.reply_text(
                    message_text,
                    parse_mode='HTML'
                ,
            protect_content=True
        )

# ========== ВІЗОВА АНКЕТА - ПОЧАТОК ==========

visa_form_storage = {}

# Список з 20 повідомлень для розсилки
NOTIFICATION_MESSAGES = [
    ("🔥 Новые вакансии на складах DHL (Германия)!\nСтабильная работа, жильё предоставляют, зарплата от €3 700.\nПроверь, пока набор открыт 👉", "Посмотреть"),
    ("🌍 Появились новые рабочие места без знания языка.\nЖильё предоставляют, условия отличные.\nПосмотри, пока набор идёт 👉", "Посмотреть"),
    ("💼 Начали приём заявок в логистическую компанию GLS.\nРабота без языка, жильё и трансфер включены.\nКоличество мест ограничено 👉", "Перейти"),
    ("🍃 Появились вакансии на фабрике Lipton.\nБез знания языка, стабильная ставка около €3 600.\nПриём документов открыт 👉", "Подробнее"),
    ("📢 Поступили вакансии на упаковку товаров в Германии и Англии.\nЖильё предоставляется, оформление быстрое.\nПроверить 👉", "Смотреть"),
    ("🔥 Сегодня стартовал набор на Amazon Warehouse (Англия).\nЗарплата от £3 300, жильё предоставляется.\nПроверь детали 👉", "Смотреть"),
    ("📦 В Германии открыт набор в DHL.\nСортировка посылок, стабильная ставка от €3 700 в месяц.\nОформление быстрое 👉", "Подробнее"),
    ("🏠 Вакансии на складах IKEA Германия.\nЗарплата от €3 800, жильё предоставляется.\nЗнание языка не требуется 👉", "Посмотреть"),
    ("💼 Новая группа выезда в FedEx Германия.\nОсталось 4 рабочих места, зарплата до €4 200, выезд через 5 недель 👉", "Посмотреть"),
    ("🏭 На завод Volkswagen требуются сотрудники на сборочную линию.\nДоход от €3 900, официальное оформление.\nУспей подать заявку 👉", "Перейти"),
    ("🔥 Осталось 3 свободных места на складе DHL (Германия).\nПосле этого набор закроют до следующего месяца.\nПодавай заявку сейчас — условия реально выгодные 👉", "Смотреть"),
    ("🚨 Только до завтра можно попасть в группу выезда с оплаченным билетом и жильём.\nНе упусти выгодные условия 👉", "Перейти"),
    ("Появилась крутая вакансия на заводе Volkswagen — официальное оформление, жильё рядом с производством.\nОплата до €4 200, но набор всего на 4 человека.\nХочешь, добавлю тебя в список, чтобы успел?", "Смотреть"),
    ("Привет 👋\nОсвободились места в Германии на складах.\nРаботодатель оплачивает жильё и частично перелёт.\nЕсли актуально — глянь 👉", "Посмотреть"),
    ("🔥 У нас снова открылись вакансии на складах.\nЖильё предоставляют, язык не требуется.\nУзнай, какие места доступны 👉", "Перейти"),
    ("📬 В Royal Mail (Англия) идёт набор на сортировку писем и посылок.\nЗарплата от £3 500.\nПроверь детали 👉", "Подать заявку"),
    ("🔥 Работодатель временно взял на себя оплату жилья — всё полностью бесплатно на протяжении работы.\nТакие условия редкость, посмотри, пока действует 👉", "Посмотреть"),
    ("🌍 Для новых кандидатов работодатель оплачивает билет и проживание.\nДополнительно компенсируют первые расходы по приезду.\nОткрой детали 👉", "Подробнее"),
    ("🚀 Срочный набор! Из-за нехватки людей работодатель даёт жильё и перелёт бесплатно.\nТакая возможность открыта всего на 48 часов 👉", "Подать заявку")
]

def store_visa_answer(user_id, q_num, answer):
    """Зберегти відповідь візової анкети"""
    if user_id not in visa_form_storage:
        visa_form_storage[user_id] = {}
    visa_form_storage[user_id][f'q{q_num}'] = answer

# Старі функції видалено - тепер все працює через Google Sheets

async def send_notification_to_user(bot, user_id, message_text, button_text):
    """Надіслати повідомлення користувачу"""
    try:
        # Кнопка з callback для показу вибору вакансій
        keyboard = [[InlineKeyboardButton(button_text, callback_data="notification_show_vacancies")]]
        
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            protect_content=True
        )
        return True
    except Exception as e:
        logger.error(f"Помилка відправки користувачу {user_id}: {e}")
        return False

async def send_notifications_job(context: ContextTypes.DEFAULT_TYPE):
    """Job для оновлення лічильників та відправки нагадувань"""
    try:
        logger.info("Початок щоденного оновлення нагадувань...")
        
        # Отримуємо всі user_id з таблиці
        user_ids = get_all_users_for_notifications()
        logger.info(f"Знайдено {len(user_ids)} користувачів у таблиці")
        
        sent_count = 0
        updated_count = 0
        
        for user_id in user_ids:
            try:
                # Отримуємо поточне значення лічильника
                current_days = get_reminder_days(user_id)
                
                if current_days <= 1:
                    # Якщо лічильник 0 або 1 - надсилаємо нагадування
                    if current_days == 0:
                        # Вибираємо випадкове повідомлення
                        message_text, button_text = random.choice(NOTIFICATION_MESSAGES)
                        
                        # Надсилаємо повідомлення
                        success = await send_notification_to_user(context.bot, user_id, message_text, button_text)
                        
                        if success:
                            sent_count += 1
                            logger.info(f"Нагадування надіслано користувачу {user_id}")
                        else:
                            logger.error(f"Не вдалось надіслати нагадування користувачу {user_id}")
                    
                    # Встановлюємо знову на 7
                    update_reminder_days(user_id, 7)
                else:
                    # Зменшуємо лічильник на 1
                    update_reminder_days(user_id, current_days - 1)
                
                updated_count += 1
                    
            except Exception as e:
                logger.error(f"Помилка обробки користувача {user_id}: {e}")
        
        logger.info(f"Оновлення завершено: надіслано {sent_count}, оновлено {updated_count}")
        
    except Exception as e:
        logger.error(f"Помилка виконання job нагадувань: {e}")

async def send_notification_to_all(context: ContextTypes.DEFAULT_TYPE):
    """Відправити повідомлення всім користувачам (для першого запуску)"""
    await send_notifications_job(context)

async def start_visa_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Початок візової анкети - перше питання"""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        
        # Перевіряємо, чи вже заповнював користувач форму
        if check_user_filled_visa(user_id):
            await query.answer()
            final_message = f"""🟢 <b>Уведомление о регистрации заявки</b>

✅ Ваша заявка успешно зарегистрирована в системе.
Регистрационный номер: {user_id}

Ваши документы переданы на стадию перевода и дальнейшей проверки
и будут направлены в:
 • визовый центр,
 • консульский отдел посольства,
 • иммиграционную службу — для проверки возможности получения данного типа визы по указанным вами данным.

⏳ Обработка может занять от 1 до 3 рабочих дней.
📩 Извещение о результатах вы получите на ваш e-mail указанный в анкете выше,
в виде официального письма.

⚠️ Важно: сообщите свой регистрационный номер менеджеру для подтверждения подачи и продолжения оформления документов."""
            
            await query.edit_message_text(final_message, reply_markup=get_main_menu(), parse_mode='HTML')
            return ConversationHandler.END
        
        await query.answer()

        # Показываем первое вопрос и оставляем главное меню доступным
        await query.message.reply_text(
            "🧾 <b>I. Личные данные</b>\n\n"
            "1️⃣ <b>ФИО (как в загранпаспорте):</b>\n\n"
            "Напишите ответ ниже 👇",
            parse_mode='HTML',
            reply_markup=get_main_menu()
        )
        return VISA_Q1
    return ConversationHandler.END

# Обробники питань 1-7 (текстові)
async def visa_q1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("1️⃣ <b>ФИО (как в загранпаспорте):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q1
    store_visa_answer(user_id, 1, text)
    await update.message.reply_text("2️⃣ <b>Дата и место рождения:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q2

async def visa_q2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("2️⃣ <b>Дата и место рождения:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q2
    store_visa_answer(user_id, 2, text)
    await update.message.reply_text("3️⃣ <b>Гражданство:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q3

async def visa_q3_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("3️⃣ <b>Гражданство:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q3
    store_visa_answer(user_id, 3, text)
    await update.message.reply_text("4️⃣ <b>Паспортные данные (номер, срок действия):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q4

async def visa_q4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("4️⃣ <b>Паспортные данные (номер, срок действия):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q4
    store_visa_answer(user_id, 4, text)
    await update.message.reply_text("5️⃣ <b>Адрес проживания и прописка:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q5

async def visa_q5_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("5️⃣ <b>Адрес проживания и прописка:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q5
    store_visa_answer(user_id, 5, text)
    await update.message.reply_text("6️⃣ <b>Контактные данные (телефон, email):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q6

async def visa_q6_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("6️⃣ <b>Контактные данные (телефон, email):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q6
    store_visa_answer(user_id, 6, text)
    await update.message.reply_text("7️⃣ <b>Номер телефона мессенджеров (WhatsApp, Telegram):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q7

async def visa_q7_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("7️⃣ <b>Номер телефона мессенджеров (WhatsApp, Telegram):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q7
    store_visa_answer(user_id, 7, text)
    # Питання 8 з варіантами
    keyboard = [[InlineKeyboardButton("⚪️ В браке", callback_data="visa_q8_married")],
                [InlineKeyboardButton("⚪️ Не в браке", callback_data="visa_q8_single")]]
    await update.message.reply_text("👨‍👩‍👧‍👦 <b>II. Семья и родственные связи</b>\n\n8️⃣ <b>Семейное положение:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return VISA_Q8

# Питання 8 (вибір)
async def visa_q8_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q8_married":
        store_visa_answer(user_id, 8, "В браке")
        answer_text = "В браке"
    elif query.data == "visa_q8_single":
        store_visa_answer(user_id, 8, "Не в браке")
        answer_text = "Не в браке"
    else:
        return VISA_Q8
    await query.answer()
    await query.edit_message_text(f"8️⃣ <b>Семейное положение</b>\n\n<b>Ответ:</b> {answer_text}", parse_mode='HTML')
    await query.message.reply_text("9️⃣ <b>Родители (имена, гражданства):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
    return VISA_Q9

# Питання 9-11 (текстові)
async def visa_q9_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("9️⃣ <b>Родители (имена, гражданства):</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q9
    store_visa_answer(user_id, 9, text)
    await update.message.reply_text("🔟 <b>Супруга и дети:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q10

async def visa_q10_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("🔟 <b>Супруга и дети:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q10
    store_visa_answer(user_id, 10, text)
    await update.message.reply_text("1️⃣1️⃣ <b>Родственные связи в стране назначения:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
    return VISA_Q11

async def visa_q11_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("1️⃣1️⃣ <b>Родственные связи в стране назначения:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q11
    store_visa_answer(user_id, 11, text)
    # Питання 12 з варіантами
    keyboard = [[InlineKeyboardButton("⚪️ Школа", callback_data="visa_q12_school")],
                [InlineKeyboardButton("⚪️ Колледж", callback_data="visa_q12_college")],
                [InlineKeyboardButton("⚪️ Университет", callback_data="visa_q12_university")]]
    await update.message.reply_text("🎓 <b>III. Образование и профессиональный опыт</b>\n\n1️⃣2️⃣ <b>Уровень образования:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return VISA_Q12

# Питання 12 (вибір)
async def visa_q12_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q12_school": "Школа", "visa_q12_college": "Колледж", "visa_q12_university": "Университет"}
    if query.data in answers:
        store_visa_answer(user_id, 12, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"1️⃣2️⃣ <b>Уровень образования</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        await query.message.reply_text("1️⃣3️⃣ <b>Профессиональный опыт (последние места работы, должности, обязанности)?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q13
    return VISA_Q12

# Питання 13 (текст)
async def visa_q13_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("1️⃣3️⃣ <b>Профессиональный опыт (последние места работы, должности, обязанности)?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML', reply_markup=get_main_menu())
        return VISA_Q13
    store_visa_answer(user_id, 13, text)
    # Питання 14 з варіантами
    keyboard = [[InlineKeyboardButton("⚪️ Да (указать какие)", callback_data="visa_q14_yes")],
                [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q14_no")]]
    await update.message.reply_text("1️⃣4️⃣ <b>Владение иностранных языков?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return VISA_Q14

# Питання 14 (вибір)
async def visa_q14_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q14_yes":
        store_visa_answer(user_id, 14, "Да")
        await query.answer()
        await query.edit_message_text(f"1️⃣4️⃣ <b>Владение иностранных языков?</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        # Питаємо деталі
        await query.message.reply_text("💬 <b>Укажите какие языки:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q14_DETAIL
    elif query.data == "visa_q14_no":
        store_visa_answer(user_id, 14, "Нет")
        await query.answer()
        await query.edit_message_text(f"1️⃣4️⃣ <b>Владение иностранных языков?</b>\n\n<b>Ответ:</b> Нет", parse_mode='HTML')
        # Питання 15
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q15_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q15_no")]]
        await query.message.reply_text("1️⃣5️⃣ <b>Наличие водительских прав?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q15
    return VISA_Q14

# Q14 деталі
async def visa_q14_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    store_visa_answer(user_id, 14, f"Да: {text}")
    await update.message.reply_text(
        "1️⃣5️⃣ <b>Наличие водительских прав?</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚪️ Да", callback_data="visa_q15_yes")],
                                           [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q15_no")]]),
        parse_mode='HTML'
    )
    return VISA_Q15

# Питання 15 (вибір)
async def visa_q15_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q15_yes":
        store_visa_answer(user_id, 15, "Да")
        await query.answer()
        await query.edit_message_text(f"1️⃣5️⃣ <b>Наличие водительских прав?</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        # Питаємо деталі
        await query.message.reply_text("💬 <b>Укажите категории прав:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q15_DETAIL
    elif query.data == "visa_q15_no":
        store_visa_answer(user_id, 15, "Нет")
        await query.answer()
        await query.edit_message_text(f"1️⃣5️⃣ <b>Наличие водительских прав?</b>\n\n<b>Ответ:</b> Нет", parse_mode='HTML')
        # Питання 16
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q16_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q16_no")]]
        await query.message.reply_text("1️⃣6️⃣ <b>Есть ли опыт работы за границей?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q16
    return VISA_Q15

# Q15 деталі
async def visa_q15_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    store_visa_answer(user_id, 15, f"Да: {text}")
    await update.message.reply_text(
        "1️⃣6️⃣ <b>Есть ли опыт работы за границей?</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚪️ Да", callback_data="visa_q16_yes")],
                                           [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q16_no")]]),
        parse_mode='HTML'
    )
    return VISA_Q16

# Питання 16 (вибір)
async def visa_q16_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q16_yes": "Да", "visa_q16_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 16, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"1️⃣6️⃣ <b>Есть ли опыт работы за границей?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        # Питання 17
        keyboard = [[InlineKeyboardButton("⚪️ Работа", callback_data="visa_q17_work")],
                    [InlineKeyboardButton("⚪️ Учёба", callback_data="visa_q17_study")],
                    [InlineKeyboardButton("⚪️ Лечение", callback_data="visa_q17_treatment")]]
        await query.message.reply_text("🌍 <b>IV. Цель и планы пребывания</b>\n\n1️⃣7️⃣ <b>Цель въезда в страну:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q17
    return VISA_Q16

# Питання 17 (вибір)
async def visa_q17_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q17_work": "Работа", "visa_q17_study": "Учёба", "visa_q17_treatment": "Лечение"}
    if query.data in answers:
        store_visa_answer(user_id, 17, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"1️⃣7️⃣ <b>Цель въезда в страну:</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        await query.message.reply_text("1️⃣8️⃣ <b>В какой стране вы планируете работать сейчас?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q18
    return VISA_Q17

# Питання 18-19 (текстові)
async def visa_q18_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("1️⃣8️⃣ <b>В какой стране вы планируете работать сейчас?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q18
    store_visa_answer(user_id, 18, text)
    await update.message.reply_text("1️⃣9️⃣ <b>Почему выбрали именно эту страну?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
    return VISA_Q19

async def visa_q19_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("1️⃣9️⃣ <b>Почему выбрали именно эту страну?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q19
    store_visa_answer(user_id, 19, text)
    # Питання 20
    keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q20_yes")],
                [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q20_no")]]
    await update.message.reply_text("2️⃣0️⃣ <b>Есть ли желание получить долгосрочную визу / ВНЖ?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return VISA_Q20

# Питання 20 (вибір)
async def visa_q20_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q20_yes": "Да", "visa_q20_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 20, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣0️⃣ <b>Есть ли желание получить долгосрочную визу / ВНЖ?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        # Питання 21
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q21_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q21_no")]]
        await query.message.reply_text("2️⃣1️⃣ <b>Планируете ли вы возвращаться на родину после окончания контракта?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q21
    return VISA_Q20

# Питання 21 (вибір)
async def visa_q21_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q21_yes": "Да", "visa_q21_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 21, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣1️⃣ <b>Планируете ли вы возвращаться на родину после окончания контракта?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        # Питання 22
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q22_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q22_no")]]
        await query.message.reply_text("🧾 <b>V. Визы, ограничения и правовой статус</b>\n\n2️⃣2️⃣ <b>Есть ли визовые отказы?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q22
    return VISA_Q21

# Питання 22-26 (вибір)
async def visa_q22_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q22_yes": "Да", "visa_q22_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 22, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣2️⃣ <b>Есть ли визовые отказы?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q23_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q23_no")]]
        await query.message.reply_text("2️⃣3️⃣ <b>Депортации или запреты на въезд?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q23
    return VISA_Q22

async def visa_q23_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q23_yes":
        store_visa_answer(user_id, 23, "Да")
        await query.answer()
        await query.edit_message_text(f"2️⃣3️⃣ <b>Депортации или запреты на въезд?</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        # Питаємо деталі
        await query.message.reply_text("💬 <b>В какой стране?</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q23_DETAIL
    elif query.data == "visa_q23_no":
        store_visa_answer(user_id, 23, "Нет")
        await query.answer()
        await query.edit_message_text(f"2️⃣3️⃣ <b>Депортации или запреты на въезд?</b>\n\n<b>Ответ:</b> Нет", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q24_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q24_no")]]
        await query.message.reply_text("2️⃣4️⃣ <b>Судимости, уголовные дела или административные наказания?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q24
    return VISA_Q23

# Q23 деталі
async def visa_q23_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    store_visa_answer(user_id, 23, f"Да: {text}")
    await update.message.reply_text(
        "2️⃣4️⃣ <b>Судимости, уголовные дела или административные наказания?</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚪️ Да", callback_data="visa_q24_yes")],
                                           [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q24_no")]]),
        parse_mode='HTML'
    )
    return VISA_Q24

async def visa_q24_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q24_yes": "Да", "visa_q24_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 24, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣4️⃣ <b>Судимости, уголовные дела или административные наказания?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q25_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q25_no")]]
        await query.message.reply_text("2️⃣5️⃣ <b>Есть ли у вас открытые дела в полиции или суде в вашей стране?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q25
    return VISA_Q24

async def visa_q25_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q25_yes": "Да", "visa_q25_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 25, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣5️⃣ <b>Есть ли у вас открытые дела в полиции или суде в вашей стране?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q26_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q26_no")]]
        await query.message.reply_text("2️⃣6️⃣ <b>Участие в военных конфликтах, террористических или запрещенных организациях?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q26
    return VISA_Q25

async def visa_q26_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q26_yes": "Да", "visa_q26_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 26, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣6️⃣ <b>Участие в военных конфликтах, террористических или запрещенных организациях?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q27_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q27_no")]]
        await query.message.reply_text("💰 <b>VI. Финансы и здоровье</b>\n\n2️⃣7️⃣ <b>Имеете ли вы достаточные финансовые средства для покрытия всех расходов?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q27
    return VISA_Q26

async def visa_q27_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    answers = {"visa_q27_yes": "Да", "visa_q27_no": "Нет"}
    if query.data in answers:
        store_visa_answer(user_id, 27, answers[query.data])
        await query.answer()
        await query.edit_message_text(f"2️⃣7️⃣ <b>Имеете ли вы достаточные финансовые средства для покрытия всех расходов?</b>\n\n<b>Ответ:</b> {answers[query.data]}", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q28_yes")],
                    [InlineKeyboardButton("⚪️ Нет", callback_data="visa_q28_no")]]
        await query.message.reply_text("2️⃣8️⃣ <b>Есть ли хронические заболевания?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q28
    return VISA_Q27

async def visa_q28_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q28_yes":
        store_visa_answer(user_id, 28, "Да")
        await query.answer()
        await query.edit_message_text(f"2️⃣8️⃣ <b>Есть ли хронические заболевания?</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        # Питаємо деталі
        await query.message.reply_text("💬 <b>Укажите какие:</b>\n\nНапишите ответ ниже 👇", parse_mode='HTML')
        return VISA_Q28_DETAIL
    elif query.data == "visa_q28_no":
        store_visa_answer(user_id, 28, "Нет")
        await query.answer()
        await query.edit_message_text(f"2️⃣8️⃣ <b>Есть ли хронические заболевания?</b>\n\n<b>Ответ:</b> Нет", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q29_yes")]]
        await query.message.reply_text("✅ <b>VII. Подтверждения и согласия</b>\n\n2️⃣9️⃣ <b>Подтверждаете ли вы достоверность предоставленных данных?</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q29
    return VISA_Q28

# Q28 деталі
async def visa_q28_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    if is_main_menu_text(text):
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        await text_handler(update, context)
        return ConversationHandler.END
    store_visa_answer(user_id, 28, f"Да: {text}")
    await update.message.reply_text(
        "✅ <b>VII. Подтверждения и согласия</b>\n\n2️⃣9️⃣ <b>Подтверждаете ли вы достоверность предоставленных данных?</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚪️ Да", callback_data="visa_q29_yes")]]),
        parse_mode='HTML'
    )
    return VISA_Q29

async def visa_q29_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q29_yes":
        store_visa_answer(user_id, 29, "Да")
        await query.answer()
        await query.edit_message_text(f"2️⃣9️⃣ <b>Подтверждаете ли вы достоверность предоставленных данных?</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        keyboard = [[InlineKeyboardButton("⚪️ Да", callback_data="visa_q30_yes")]]
        await query.message.reply_text("3️⃣0️⃣ <b>Согласен(а) на обработку персональных данных</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return VISA_Q30
    return VISA_Q29

async def visa_q30_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == "visa_q30_yes":
        store_visa_answer(user_id, 30, "Да")
        await query.answer()
        await query.edit_message_text(f"3️⃣0️⃣ <b>Согласен(а) на обработку персональных данных</b>\n\n<b>Ответ:</b> Да", parse_mode='HTML')
        
        # Отправить в канал
        user_form_data = visa_form_storage.get(user_id, {})
        message = f"""🛂 <b>ВИЗОВА АНКЕТА</b>

<b>Регистрационный номер:</b> {user_id}

<b>ФИО:</b> {user_form_data.get('q1', '')}
<b>Дата рождения:</b> {user_form_data.get('q2', '')}
<b>Гражданство:</b> {user_form_data.get('q3', '')}
<b>Паспорт:</b> {user_form_data.get('q4', '')}
<b>Адрес:</b> {user_form_data.get('q5', '')}
<b>Контакты:</b> {user_form_data.get('q6', '')}
<b>Мессенджеры:</b> {user_form_data.get('q7', '')}
<b>Семейное положение:</b> {user_form_data.get('q8', '')}
<b>Родители:</b> {user_form_data.get('q9', '')}
<b>Супруга/дети:</b> {user_form_data.get('q10', '')}
<b>Родственные связи:</b> {user_form_data.get('q11', '')}

<b>Образование:</b> {user_form_data.get('q12', '')}
<b>Опыт:</b> {user_form_data.get('q13', '')}
<b>Языки:</b> {user_form_data.get('q14', '')}
<b>Права:</b> {user_form_data.get('q15', '')}
<b>Опыт за границей:</b> {user_form_data.get('q16', '')}

<b>Цель въезда:</b> {user_form_data.get('q17', '')}
<b>Страна работы:</b> {user_form_data.get('q18', '')}
<b>Почему страна:</b> {user_form_data.get('q19', '')}
<b>Желание ВНЖ:</b> {user_form_data.get('q20', '')}
<b>Возвращение:</b> {user_form_data.get('q21', '')}

<b>Визовые отказы:</b> {user_form_data.get('q22', '')}
<b>Депортации:</b> {user_form_data.get('q23', '')}
<b>Судимости:</b> {user_form_data.get('q24', '')}
<b>Открытые дела:</b> {user_form_data.get('q25', '')}
<b>Конфликты:</b> {user_form_data.get('q26', '')}

<b>Финансы:</b> {user_form_data.get('q27', '')}
<b>Заболевания:</b> {user_form_data.get('q28', '')}
<b>Подтверждение:</b> {user_form_data.get('q29', '')}
<b>Согласие:</b> {user_form_data.get('q30', '')}

<b>ID:</b> {user_id} | <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        await context.bot.send_message(chat_id=APPLICATIONS_CHANNEL_ID, text=message, parse_mode='HTML', protect_content=True)
        
        # Запис в Google Sheets
        save_visa_filled(user_id)
        
        # Фінальне повідомлення користувачу
        final_message = f"""🟢 <b>Уведомление о регистрации заявки</b>

✅ Ваша заявка успешно зарегистрирована в системе.
Регистрационный номер: {user_id}

Ваши документы переданы на стадию перевода и дальнейшей проверки
и будут направлены в:
 • визовый центр,
 • консульский отдел посольства,
 • иммиграционную службу — для проверки возможности получения данного типа визы по указанным вами данным.

⏳ Обработка может занять от 1 до 3 рабочих дней.
📩 Извещение о результатах вы получите на ваш e-mail указанный в анкете выше,
в виде официального письма.

⚠️ Важно: сообщите свой регистрационный номер менеджеру для подтверждения подачи и продолжения оформления документов."""
        await query.message.reply_text(final_message, reply_markup=get_main_menu(), parse_mode='HTML')
        
        # Очистка
        if user_id in visa_form_storage:
            del visa_form_storage[user_id]
        
        return ConversationHandler.END
    return VISA_Q30

async def cancel_visa_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасувати візову анкету"""
    user_id = update.message.from_user.id
    if user_id in visa_form_storage:
        del visa_form_storage[user_id]
    await update.message.reply_text("❌ Заполнение анкеты отменено.", parse_mode='HTML')
    return ConversationHandler.END

# ========== ВІЗОВА АНКЕТА - КІНЕЦЬ ==========

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибку и уведомляет разработчика."""
    logger.error("Exception while handling an update:", exc_info=context.error)

async def send_notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для тестування - показує випадкове повідомлення"""
    try:
        user_id = update.effective_user.id
        
        # Вибираємо випадкове повідомлення
        message_text, button_text = random.choice(NOTIFICATION_MESSAGES)
        
        # Надсилаємо повідомлення адміну
        keyboard = [[InlineKeyboardButton(button_text, callback_data="notification_show_vacancies")]]
        
        await update.message.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            protect_content=True
        )
        
        # Тестуємо нову job для оновлення
        await send_notifications_job(context)
        
    except Exception as e:
        logger.error(f"Помилка тестової відправки: {e}")
        await update.message.reply_text(f"❌ Помилка: {e}", protect_content=True)

def main():
    import time
    import subprocess
    import os
    import platform
    
    print("Завершаем все предыдущие запуски Python...")
    try:
        if platform.system() == 'Windows':
            current_pid = os.getpid()
            result = subprocess.run(['wmic', 'process', 'where', 'name="python.exe"', 'get', 'ProcessId', '/format:list'], 
                                  capture_output=True, text=True, check=False)
            if result.stdout:
                pids = []
                for line in result.stdout.split('\n'):
                    if 'ProcessId=' in line:
                        pid = line.split('=')[1].strip()
                        if pid and int(pid) != current_pid:
                            pids.append(pid)
                for pid in pids:
                    try:
                        subprocess.run(['taskkill', '/F', '/PID', pid], 
                                      capture_output=True, text=True, check=False)
                    except:
                        pass
                print(f"Завершено {len(pids)} процессов Python")
            else:
                print("Предыдущих процессов Python не найдено")
        else:
            print("Не Windows среда — пропускаем завершение процессов.")
    except Exception as e:
        print(f"Ошибка при завершении процессов: {e}")
    
    print("Очищаем соединение...")
    time.sleep(5)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    
    
    form_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_form, pattern="^apply_")],
        states={
            FORM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, form_name_handler)],
            FORM_BIRTH_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, form_birth_date_handler)],
            FORM_CITIZENSHIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, form_citizenship_handler)],
            FORM_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, form_location_handler)],
            FORM_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, form_contact_handler)],
            FORM_WORK_SEEKING: [
                CallbackQueryHandler(form_work_seeking_handler, pattern="^work_(self|friends|couple)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_work_seeking_handler)
            ],
            FORM_PASSPORT: [
                CallbackQueryHandler(form_passport_handler, pattern="^passport_(yes|process|no)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_passport_handler)
            ],
            FORM_VISA_DOCS: [
                CallbackQueryHandler(form_visa_docs_handler, pattern="^visa_(yes|no)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_visa_docs_handler)
            ],
            FORM_DIFFICULTIES: [
                CallbackQueryHandler(form_difficulties_handler, pattern="^diff_(no|small|deport|never)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_difficulties_handler)
            ],
            FORM_READY_SPEED: [
                CallbackQueryHandler(form_ready_speed_handler, pattern="^speed_(now|later|unsure)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_ready_speed_handler)
            ],
            FORM_FINANCIAL_ABILITY: [
                CallbackQueryHandler(form_financial_ability_handler, pattern="^money_(yes|soon|no)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_financial_ability_handler)
            ],
            FORM_IMMEDIATE_START: [
                CallbackQueryHandler(form_immediate_start_handler, pattern="^ready_(yes|need_time|unsure)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_immediate_start_handler)
            ],
            FORM_VISA_TERM: [
                CallbackQueryHandler(form_visa_term_handler, pattern="^term_(6|12|other)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_visa_term_handler)
            ]
        },
        # Прерываем заполнение формы ТОЛЬКО при нажатии кнопок главного меню
        fallbacks=[
            MessageHandler(
                filters.Regex(r"^(🧾 Вакансии|✅ Гарантии|💬 Связаться с менеджером|❓ Вопрос - ответ|🔄 Как мы работаем|ℹ️ О нас|📍 Контакты)$"),
                cancel_form
            )
        ]
    )
    
    # Візова анкета handler
    visa_form_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_visa_form, pattern="^start_visa_form$")],
        states={
            VISA_Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q1_handler)],
            VISA_Q2: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q2_handler)],
            VISA_Q3: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q3_handler)],
            VISA_Q4: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q4_handler)],
            VISA_Q5: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q5_handler)],
            VISA_Q6: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q6_handler)],
            VISA_Q7: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q7_handler)],
            VISA_Q8: [CallbackQueryHandler(visa_q8_handler, pattern="^visa_q8_")],
            VISA_Q9: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q9_handler)],
            VISA_Q10: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q10_handler)],
            VISA_Q11: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q11_handler)],
            VISA_Q12: [CallbackQueryHandler(visa_q12_handler, pattern="^visa_q12_")],
            VISA_Q13: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q13_handler)],
            VISA_Q14: [CallbackQueryHandler(visa_q14_handler, pattern="^visa_q14_")],
            VISA_Q14_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q14_detail_handler)],
            VISA_Q15: [CallbackQueryHandler(visa_q15_handler, pattern="^visa_q15_")],
            VISA_Q15_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q15_detail_handler)],
            VISA_Q16: [CallbackQueryHandler(visa_q16_handler, pattern="^visa_q16_")],
            VISA_Q17: [CallbackQueryHandler(visa_q17_handler, pattern="^visa_q17_")],
            VISA_Q18: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q18_handler)],
            VISA_Q19: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q19_handler)],
            VISA_Q20: [CallbackQueryHandler(visa_q20_handler, pattern="^visa_q20_")],
            VISA_Q21: [CallbackQueryHandler(visa_q21_handler, pattern="^visa_q21_")],
            VISA_Q22: [CallbackQueryHandler(visa_q22_handler, pattern="^visa_q22_")],
            VISA_Q23: [CallbackQueryHandler(visa_q23_handler, pattern="^visa_q23_")],
            VISA_Q23_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q23_detail_handler)],
            VISA_Q24: [CallbackQueryHandler(visa_q24_handler, pattern="^visa_q24_")],
            VISA_Q25: [CallbackQueryHandler(visa_q25_handler, pattern="^visa_q25_")],
            VISA_Q26: [CallbackQueryHandler(visa_q26_handler, pattern="^visa_q26_")],
            VISA_Q27: [CallbackQueryHandler(visa_q27_handler, pattern="^visa_q27_")],
            VISA_Q28: [CallbackQueryHandler(visa_q28_handler, pattern="^visa_q28_")],
            VISA_Q28_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, visa_q28_detail_handler)],
            VISA_Q29: [CallbackQueryHandler(visa_q29_handler, pattern="^visa_q29_")],
            VISA_Q30: [CallbackQueryHandler(visa_q30_handler, pattern="^visa_q30_")],
        },
        # Прерываем визовую анкету ТОЛЬКО при нажатии кнопок главного меню
        fallbacks=[
            MessageHandler(
                filters.Regex(r"^(🧾 Вакансии|✅ Гарантии|💬 Связаться с менеджером|❓ Вопрос - ответ|🔄 Как мы работаем|ℹ️ О нас|📍 Контакты)$"),
                cancel_visa_form
            )
        ]
    )
    
    application.add_handler(form_conv_handler)
    application.add_handler(visa_form_handler)  # Візова анкета
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("send_notifications", send_notifications_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_error_handler(error_handler)
    
    # Налаштування щоденного відправлення повідомлень (кожні 24 години)
    # Зазначте: для роботи потрібно встановити: pip install "python-telegram-bot[job-queue]"
    # Для тестування використовуйте команду /send_notifications
    # application.job_queue.run_repeating(send_notifications_job, interval=86400, first=10)
    
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
