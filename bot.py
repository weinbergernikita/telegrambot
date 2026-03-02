#!/usr/bin/env python3
import logging
import os
import sqlite3
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ========== НАСТРОЙКИ ==========
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

# База данных
DATABASE_NAME = "service_bot.db"
REQUESTS_PER_PAGE = 5  # для пагинации в админке

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    raise ValueError("BOT_TOKEN не настроен")

# ========== БАЗА ДАННЫХ ==========
def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS repair_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                client_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                problem_type TEXT NOT NULL,
                problem_description TEXT NOT NULL,
                status TEXT DEFAULT 'Новая',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    logger.info("✅ База данных готова")

# --- Работа с заявками ---
def add_request(user_id, username, client_name, phone, problem_type, problem_description):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO repair_requests 
            (user_id, username, client_name, phone, problem_type, problem_description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, client_name, phone, problem_type, problem_description))
        conn.commit()
        return cur.lastrowid

def get_user_requests(user_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT id, problem_type, problem_description, status, created_at
            FROM repair_requests
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        return [dict(row) for row in cur.fetchall()]

def get_all_requests():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM repair_requests ORDER BY created_at DESC')
        return [dict(row) for row in cur.fetchall()]

def get_requests_by_status(status):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM repair_requests WHERE status = ? ORDER BY created_at DESC', (status,))
        return [dict(row) for row in cur.fetchall()]

def get_request_by_id(request_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM repair_requests WHERE id = ?', (request_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def update_request_status(request_id, new_status):
    with get_connection() as conn:
        conn.execute('UPDATE repair_requests SET status = ? WHERE id = ?', (new_status, request_id))

def delete_request(request_id):
    with get_connection() as conn:
        conn.execute('DELETE FROM repair_requests WHERE id = ?', (request_id,))

def get_requests_stats():
    with get_connection() as conn:
        cur = conn.cursor()
        total = cur.execute('SELECT COUNT(*) FROM repair_requests').fetchone()[0]
        today = cur.execute('SELECT COUNT(*) FROM repair_requests WHERE DATE(created_at) = DATE("now")').fetchone()[0]
        cur.execute('SELECT status, COUNT(*) FROM repair_requests GROUP BY status')
        by_status = dict(cur.fetchall())
        return {'total': total, 'today': today, 'by_status': by_status}

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========
def validate_phone(phone):
    digits = ''.join(filter(str.isdigit, phone))
    return 10 <= len(digits) <= 11

def status_emoji(status):
    return {'Новая': '🆕', 'В работе': '⚙️', 'Готово': '✅'}.get(status, '📌')

# ========== КЛАВИАТУРЫ (ПОЛНОСТЬЮ СОХРАНЕНЫ ОРИГИНАЛЬНЫЕ) ==========
def get_main_menu():
    """Главное меню (добавлена кнопка 'Мои заявки')"""
    buttons = [
        [InlineKeyboardButton("🆘 Создать заявку", callback_data="create")],
        [InlineKeyboardButton("📋 Мои заявки", callback_data="my_requests")],  # НОВАЯ КНОПКА
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts")],
        [InlineKeyboardButton("💰 Цены", callback_data="prices")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_problems_menu():
    """Меню выбора проблемы (оригинальное)"""
    buttons = [
        [InlineKeyboardButton("💻 Не включается", callback_data="problem_not_starting")],
        [InlineKeyboardButton("🖥️ Медленно работает", callback_data="problem_slow")],
        [InlineKeyboardButton("🌡️ Перегревается", callback_data="problem_overheating")],
        [InlineKeyboardButton("🖨️ Проблема с оргтехникой", callback_data="problem_office")],
        [InlineKeyboardButton("💿 Проблема с програмным обеспечением", callback_data="problem_software")],
        [InlineKeyboardButton("🌐 Нет интернета", callback_data="problem_internet")],
        [InlineKeyboardButton("❓ Другая проблема", callback_data="problem_other")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(buttons)

# ========== ХРАНЕНИЕ СОСТОЯНИЙ (ВРЕМЕННОЕ) ==========
user_states = {}  # вместо user_data, чтобы не конфликтовать с БД

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = f"""👋 Здравствуйте, {user.first_name}!

🛠️ *Сервисный центр по ремонту и обслуживанию компьютеров*

Мы поможем с любой проблемой:
• Диагностика - бесплатно
• Быстрый ремонт
• Широкий спектр услуг

Выберите действие:"""
    await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Доступные команды:*\n"
        "/start - Начать работу с ботом\n"
        "/help - Получить справку\n"
        "/admin - Панель администратора (только для админа)\n\n"
        "Используйте кнопки меню для навигации.",
        parse_mode="Markdown"
    )

# ========== АДМИН-ПАНЕЛЬ (ТОЛЬКО КНОПКИ) ==========
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в админ-панель по команде /admin"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав для этой команды.")
        return

    await show_admin_main_menu(update.message)

async def show_admin_main_menu(message):
    text = "🔐 **Панель администратора**\n\nВыберите действие:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Все заявки", callback_data="admin_all")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🆕 Новые", callback_data="admin_status_Новая")],
        [InlineKeyboardButton("⚙️ В работе", callback_data="admin_status_В работе")],
        [InlineKeyboardButton("✅ Готово", callback_data="admin_status_Готово")]
    ])
    await message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех кнопок админ-панели"""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Доступ запрещён!", show_alert=True)
        return

    data = query.data

    if data == "admin_main":
        await show_admin_main_menu(query.message)

    elif data == "admin_stats":
        stats = get_requests_stats()
        text = (
            f"📊 **Статистика заявок**\n\n"
            f"📌 Всего: **{stats['total']}**\n"
            f"📅 За сегодня: **{stats['today']}**\n\n"
            f"🆕 Новых: **{stats['by_status'].get('Новая', 0)}**\n"
            f"⚙️ В работе: **{stats['by_status'].get('В работе', 0)}**\n"
            f"✅ Готово: **{stats['by_status'].get('Готово', 0)}**"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_main")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    elif data.startswith("admin_all"):
        page = 0
        if data.startswith("admin_all_page_"):
            page = int(data.split("_")[-1])
        await show_admin_requests_page(query, page, "all")

    elif data.startswith("admin_status_") and "_page_" not in data:
        status = data.replace("admin_status_", "")
        await show_admin_requests_page(query, 0, "status", status)

    elif data.startswith("admin_status_") and "_page_" in data:
        parts = data.split("_page_")
        status = parts[0].replace("admin_status_", "")
        page = int(parts[1])
        await show_admin_requests_page(query, page, "status", status)

    elif data.startswith("admin_manage_"):
        request_id = int(data.split("_")[-1])
        req = get_request_by_id(request_id)
        if not req:
            await query.edit_message_text("❌ Заявка не найдена")
            return

        text = (
            f"🔧 **Управление заявкой №{req['id']}**\n\n"
            f"👤 **Клиент:** {req['client_name']}\n"
            f"📞 **Телефон:** {req['phone']}\n"
            f"🆔 **Username:** @{req['username'] or 'нет'}\n"
            f"🔧 **Проблема:** {req['problem_type']}\n"
            f"📝 **Описание:** {req['problem_description']}\n"
            f"📅 **Создана:** {req['created_at']}\n"
            f"🔹 **Статус:** {status_emoji(req['status'])} {req['status']}"
        )
        keyboard = get_admin_manage_keyboard(request_id, req['status'])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    elif data.startswith("admin_status_change_"):
        parts = data.split("_")
        request_id = int(parts[3])
        new_status = parts[4]
        update_request_status(request_id, new_status)

        # Уведомить клиента
        req = get_request_by_id(request_id)
        if req:
            try:
                await context.bot.send_message(
                    req['user_id'],
                    f"{status_emoji(new_status)} **Статус заявки №{request_id} изменён!**\n\nНовый статус: **{new_status}**",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить клиента: {e}")

        # Вернуться к управлению
        query.data = f"admin_manage_{request_id}"
        await admin_callback_handler(update, context)

    elif data.startswith("admin_contact_"):
        request_id = int(data.split("_")[-1])
        req = get_request_by_id(request_id)
        if req:
            text = (
                f"📞 **Контакты клиента**\n\n"
                f"👤 **Имя:** {req['client_name']}\n"
                f"📱 **Телефон:** {req['phone']}\n"
                f"🆔 **Telegram ID:** `{req['user_id']}`\n"
                f"📱 **Username:** @{req['username'] or 'не указан'}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Написать", url=f"tg://user?id={req['user_id']}")],
                [InlineKeyboardButton("◀️ Назад", callback_data=f"admin_manage_{request_id}")]
            ])
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    elif data.startswith("admin_delete_"):
        request_id = int(data.split("_")[-1])
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да", callback_data=f"admin_confirm_delete_{request_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"admin_manage_{request_id}")
            ]
        ])
        await query.edit_message_text(f"⚠️ **Удалить заявку №{request_id}?**", reply_markup=keyboard, parse_mode="Markdown")

    elif data.startswith("admin_confirm_delete_"):
        request_id = int(data.split("_")[-1])
        delete_request(request_id)
        await query.edit_message_text(
            f"✅ Заявка №{request_id} удалена.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К списку", callback_data="admin_all")]])
        )

    elif data == "admin_back_to_list":
        query.data = "admin_all"
        await admin_callback_handler(update, context)

    elif data == "ignore":
        pass

def get_admin_manage_keyboard(request_id, current_status):
    buttons = []
    # Кнопки изменения статуса
    status_row = []
    for status in ["Новая", "В работе", "Готово"]:
        if status != current_status:
            status_row.append(InlineKeyboardButton(
                f"{status_emoji(status)} {status}",
                callback_data=f"admin_status_change_{request_id}_{status}"
            ))
    if status_row:
        buttons.append(status_row)

    buttons.append([
        InlineKeyboardButton("🗑 Удалить", callback_data=f"admin_delete_{request_id}"),
        InlineKeyboardButton("📞 Контакты", callback_data=f"admin_contact_{request_id}")
    ])
    buttons.append([InlineKeyboardButton("◀️ Назад к списку", callback_data="admin_back_to_list")])
    return InlineKeyboardMarkup(buttons)

async def show_admin_requests_page(query, page, filter_type, status=None):
    if filter_type == "all":
        all_requests = get_all_requests()
        prefix = "admin_all"
    else:
        all_requests = get_requests_by_status(status)
        prefix = f"admin_status_{status}"

    if not all_requests:
        await query.edit_message_text(
            "📭 Заявок не найдено",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_main")]])
        )
        return

    total_pages = (len(all_requests) + REQUESTS_PER_PAGE - 1) // REQUESTS_PER_PAGE
    start = page * REQUESTS_PER_PAGE
    end = start + REQUESTS_PER_PAGE
    requests_page = all_requests[start:end]

    text = f"📋 **Список заявок** (стр. {page+1}/{total_pages})\n\n"
    for req in requests_page:
        text += (
            f"{status_emoji(req['status'])} **№{req['id']}** | {req['created_at'][:16]}\n"
            f"👤 {req['client_name']} | 📞 {req['phone']}\n"
            f"📝 {req['problem_description'][:50]}...\n\n"
        )

    buttons = []
    # Кнопки для каждой заявки
    for req in requests_page:
        buttons.append([InlineKeyboardButton(
            f"🔧 Управлять №{req['id']}",
            callback_data=f"admin_manage_{req['id']}"
        )])

    # Пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_page_{page+1}"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="admin_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

# ========== ОБРАБОТЧИКИ КЛИЕНТСКИХ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки главного меню (оригинальный + новые)"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "back":
        # Возврат в главное меню
        await query.edit_message_text(
            "📋 *Главное меню*\n\nВыберите нужное действие:",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

    elif data == "create":
        # Начать создание заявки
        user_states[user_id] = {"step": "select_problem"}
        await query.edit_message_text(
            "🛠️ *Выберите тип проблемы:*\n\n"
            "Пожалуйста, укажите наиболее подходящую категорию:",
            reply_markup=get_problems_menu(),
            parse_mode="Markdown"
        )

    elif data.startswith("problem_"):
        # Пользователь выбрал проблему
        problem_type = data.replace("problem_", "")
        problem_names = {
            "not_starting": "💻 Не включается",
            "slow": "🖥️ Медленно работает",
            "overheating": "🌡️ Перегревается",
            "office": "🖨️ Проблема с оргтехникой",
            "software": "💿 Проблема с программным обеспечением",
            "internet": "🌐 Нет интернета",
            "other": "❓ Другая проблема"
        }
        problem_name = problem_names.get(problem_type, "❓ Неизвестная проблема")

        # Сохраняем проблему и переходим к запросу телефона (оригинальный порядок: проблема -> телефон -> описание)
        user_states[user_id] = {
            "step": "enter_phone",
            "problem_type": problem_type,
            "problem_name": problem_name
        }

        await query.edit_message_text(
            f"✅ Выбрано: *{problem_name}*\n\n"
            "📞 *Укажите ваш номер телефона*\n\n"
            "Напишите номер в формате:\n"
            "• +7 (XXX) XXX-XX-XX\n"
            "• 8 (XXX) XXX-XX-XX\n"
            "• или просто 10-11 цифр",
            parse_mode="Markdown"
        )

    elif data == "contacts":
        await query.edit_message_text(
            "📞 *Контакты сервиса:*\n\n"
            "📱 *Телефон:* +7 (913) 735-24-65\n"
            "📧 *Email:* doc.cyber@yandex.ru\n"
            "📍 *Адрес:* г. Обь, ул. Октябрьская, 5\n\n"
            "🕐 *График работы:*\n"
            "Пн-Пт: 9:00 - 20:00\n"
            "Сб-Вс: 10:00 - 18:00\n\n"
            "🚗 *Есть бесплатная парковка*",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back")]]),
            parse_mode="Markdown"
        )

    elif data == "prices":
        await query.edit_message_text(
            "💰 *Наши цены:*\n\n"
            "🆓 *Диагностика* - БЕСПЛАТНО\n\n"
            "🛠️ *Аппаратный ремонт:*\n"
            "• Замена комплектующих ПК: от 300 ₽\n"
            "• Замена комплектующих ноутбуков: от 2000 ₽\n\n"
            "🖨️ *Оргтехника:*\n"
            "• Обслуживание оргтехники: от 2000 ₽\n\n"
            "💿 *Программное обеспечение:*\n"
            "• Установка драйверов: от 700 ₽\n"
            "• Установка Windows/Linux: от 700 ₽\n"
            "• Настройка ПО: от 500 ₽\n"
            "• Удаление вирусов: от 1000 ₽\n\n"
            "🌡️ *Перегрев:*\n"
            "• Замена термопасты: от 800 ₽\n"
            "• Чистка системы охлаждения: от 1000 ₽\n\n"
            "*⚡ Точная цена после диагностики*",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🆘 Создать заявку", callback_data="create")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back")]
            ]),
            parse_mode="Markdown"
        )

    elif data == "my_requests":
        # Новая кнопка — показать заявки пользователя
        requests = get_user_requests(user_id)
        if not requests:
            await query.edit_message_text(
                "📭 У вас пока нет заявок.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back")]])
            )
            return

        text = "📋 *Ваши заявки:*\n\n"
        for req in requests:
            text += (
                f"🔹 *Заявка №{req['id']}* от {req['created_at'][:10]}\n"
                f"   Проблема: {req['problem_type']}\n"
                f"   Статус: {status_emoji(req['status'])} {req['status']}\n"
                f"   Описание: {req['problem_description'][:50]}...\n\n"
            )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back")]]),
            parse_mode="Markdown"
        )

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ (ОРИГИНАЛЬНАЯ ЛОГИКА + СОХРАНЕНИЕ В БД) ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    text = update.message.text

    if user_id not in user_states:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню.",
            reply_markup=get_main_menu()
        )
        return

    state = user_states[user_id]
    step = state.get("step")

    if step == "enter_phone":
        # Проверяем телефон
        if not validate_phone(text):
            await update.message.reply_text(
                "❌ *Неверный формат номера*\n\n"
                "Пожалуйста, введите корректный номер телефона:",
                parse_mode="Markdown"
            )
            return

        # Сохраняем телефон и переходим к описанию
        state["phone"] = text
        state["step"] = "enter_description"
        await update.message.reply_text(
            "📝 *Теперь подробно опишите проблему:*\n\n"
            "Напишите сообщение с описанием, например:\n"
            "• Когда началась проблема\n"
            "• Что уже пробовали сделать\n"
            "• Особые детали",
            parse_mode="Markdown"
        )

    elif step == "enter_description":
        # Сохраняем описание
        description = text
        phone = state["phone"]
        problem_name = state["problem_name"]

        # Сохраняем в базу данных
        try:
            request_id = add_request(
                user_id=user_id,
                username=user.username,
                client_name=user.full_name,
                phone=phone,
                problem_type=problem_name,
                problem_description=description
            )
            logger.info(f"✅ Заявка #{request_id} сохранена")

            # Отправляем подтверждение пользователю (оригинальный текст)
            user_request_text = f"""📋 *ВАША ЗАЯВКА ПРИНЯТА*

🔧 *Проблема:* {problem_name}
📝 *Описание:* {description}

👤 *Ваши данные:*
• Имя: {user.full_name}
• Username: @{user.username or 'не указан'}
• Телефон: {phone}
• ID: {user_id}

📅 *Время создания:* {datetime.now().strftime('%d.%m.%Y %H:%M')}

✅ *Заявка №{request_id} принята!*
Наш специалист свяжется с вами в ближайшее время.

📞 *Контакты для срочных вопросов:*
+7 (913) 735-24-65"""

            await update.message.reply_text(
                "⏳ *Обрабатываю вашу заявку...*",
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)
            await update.message.reply_text(
                user_request_text,
                parse_mode="Markdown"
                reply_markup=get_main_menu()
            )

            # Отправляем админу (оригинальное сообщение)
            if ADMIN_ID:
                admin_text = f"""🎯 *НОВАЯ ЗАЯВКА НА РЕМОНТ!*

👤 *КЛИЕНТ:*
• Имя: {user.full_name}
• Username: @{user.username or 'нет'}
• Телефон: {phone}
• ID: {user_id}

🔧 *ПРОБЛЕМА:* {problem_name}
📝 *ОПИСАНИЕ:*
{description}

📅 *ВРЕМЯ:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
🆔 *НОМЕР ЗАЯВКИ:* {request_id}

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *ТРЕБУЕТСЯ ОБРАБОТКА*"""
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_text,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки админу: {e}")

        except Exception as e:
            logger.error(f"Ошибка сохранения заявки: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении заявки. Попробуйте позже.",
                reply_markup=get_main_menu()
            )

        # Очищаем состояние
        del user_states[user_id]

# ========== ЗАПУСК ==========
def main():
    init_database()

    app = Application.builder().token(TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Клиентские кнопки (все, кроме admin_*)
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(?!admin_).*"))

    # Админские кнопки
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_.*"))

    # Текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
