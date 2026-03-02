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

# ========== НАСТРОЙКА ==========
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

# Настройки базы данных
DATABASE_NAME = "service_bot.db"
REQUESTS_PER_PAGE = 5

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверка токена
if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    raise ValueError("BOT_TOKEN не настроен")

# ========== БАЗА ДАННЫХ ==========
def get_connection():
    """Создает соединение с БД"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализация базы данных"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
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
        conn.commit()
    logger.info("✅ База данных инициализирована")

def add_request(user_id, username, client_name, phone, problem_type, problem_description):
    """Добавление новой заявки"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO repair_requests 
            (user_id, username, client_name, phone, problem_type, problem_description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, client_name, phone, problem_type, problem_description))
        conn.commit()
        return cursor.lastrowid

def get_user_requests(user_id):
    """Получение заявок пользователя"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, problem_type, problem_description, status, created_at
            FROM repair_requests
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_requests():
    """Получение всех заявок"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM repair_requests ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]

def get_requests_by_status(status):
    """Получение заявок по статусу"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM repair_requests
            WHERE status = ?
            ORDER BY created_at DESC
        ''', (status,))
        return [dict(row) for row in cursor.fetchall()]

def get_request_by_id(request_id):
    """Получение заявки по ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM repair_requests WHERE id = ?', (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_request_status(request_id, new_status):
    """Обновление статуса заявки"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE repair_requests SET status = ? WHERE id = ?', (new_status, request_id))
        conn.commit()

def delete_request(request_id):
    """Удаление заявки"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM repair_requests WHERE id = ?', (request_id,))
        conn.commit()

def get_requests_stats():
    """Получение статистики"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM repair_requests')
        total = cursor.fetchone()[0]
        
        cursor.execute('SELECT status, COUNT(*) FROM repair_requests GROUP BY status')
        status_counts = dict(cursor.fetchall())
        
        cursor.execute('SELECT COUNT(*) FROM repair_requests WHERE DATE(created_at) = DATE("now")')
        today = cursor.fetchone()[0]
        
        return {
            'total': total,
            'by_status': status_counts,
            'today': today
        }

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_phone(phone):
    """Проверка номера телефона"""
    digits = ''.join(filter(str.isdigit, phone))
    return 10 <= len(digits) <= 11

def get_status_emoji(status):
    """Эмодзи для статуса"""
    emojis = {
        'Новая': '🆕',
        'В работе': '⚙️',
        'Готово': '✅'
    }
    return emojis.get(status, '📌')

# ========== КЛАВИАТУРЫ ==========
def get_main_menu():
    """Главное меню для клиентов"""
    buttons = [
        [InlineKeyboardButton("🆘 Создать заявку", callback_data="create")],
        [InlineKeyboardButton("📋 Мои заявки", callback_data="my_requests")],
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts")],
        [InlineKeyboardButton("💰 Цены", callback_data="prices")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_problems_menu():
    """Меню выбора проблемы"""
    buttons = [
        [InlineKeyboardButton("💻 Не включается", callback_data="problem_not_starting")],
        [InlineKeyboardButton("🖥️ Медленно работает", callback_data="problem_slow")],
        [InlineKeyboardButton("🌡️ Перегревается", callback_data="problem_overheating")],
        [InlineKeyboardButton("🖨️ Проблема с оргтехникой", callback_data="problem_office")],
        [InlineKeyboardButton("💿 Проблема с ПО", callback_data="problem_software")],
        [InlineKeyboardButton("🌐 Нет интернета", callback_data="problem_internet")],
        [InlineKeyboardButton("❓ Другая проблема", callback_data="problem_other")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_admin_main_menu():
    """Главное меню администратора"""
    buttons = [
        [InlineKeyboardButton("📋 Все заявки", callback_data="admin_all")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🆕 Новые заявки", callback_data="admin_status_Новая")],
        [InlineKeyboardButton("⚙️ В работе", callback_data="admin_status_В работе")],
        [InlineKeyboardButton("✅ Готово", callback_data="admin_status_Готово")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_admin_request_management_keyboard(request_id, current_status):
    """Клавиатура управления заявкой для админа"""
    buttons = []
    
    # Кнопки изменения статуса
    status_row = []
    for status in ["Новая", "В работе", "Готово"]:
        if status != current_status:
            status_row.append(
                InlineKeyboardButton(
                    f"{get_status_emoji(status)} {status}",
                    callback_data=f"admin_status_{request_id}_{status}"
                )
            )
    if status_row:
        buttons.append(status_row)
    
    # Кнопки действий
    buttons.append([
        InlineKeyboardButton("🗑 Удалить", callback_data=f"admin_delete_{request_id}"),
        InlineKeyboardButton("📞 Контакты", callback_data=f"admin_contact_{request_id}")
    ])
    
    # Кнопка назад
    buttons.append([InlineKeyboardButton("◀️ Назад к списку", callback_data="admin_back_to_list")])
    
    return InlineKeyboardMarkup(buttons)

def get_pagination_keyboard(current_page, total_pages, prefix):
    """Клавиатура пагинации"""
    buttons = []
    nav_row = []
    
    if current_page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_page_{current_page-1}"))
    
    nav_row.append(InlineKeyboardButton(f"{current_page+1}/{total_pages}", callback_data="ignore"))
    
    if current_page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_page_{current_page+1}"))
    
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="admin_main")])
    
    return InlineKeyboardMarkup(buttons)

def get_back_to_main_button():
    """Кнопка возврата в главное меню"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")
    ]])

# ========== ХРАНЕНИЕ СОСТОЯНИЙ ==========
# Временное хранение данных при создании заявки
user_states = {}

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    text = f"""👋 Здравствуйте, {user.first_name}!

🛠️ **Сервисный центр по ремонту компьютеров**

Мы поможем с любой проблемой:
• Диагностика - бесплатно
• Быстрый ремонт
• Гарантия на работы

Выберите действие:"""
    
    await update.message.reply_text(
        text, 
        reply_markup=get_main_menu(), 
        parse_mode="Markdown"
    )

# ========== ОБРАБОТЧИКИ КЛИЕНТСКОЙ ЧАСТИ ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки (клиентская часть)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Возврат в главное меню
    if data == "back_to_main":
        await query.edit_message_text(
            "📋 **Главное меню**\n\nВыберите действие:",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )
    
    # Создание заявки
    elif data == "create":
        user_states[user_id] = {"step": "select_problem"}
        await query.edit_message_text(
            "🛠️ **Выберите тип проблемы:**",
            reply_markup=get_problems_menu(),
            parse_mode="Markdown"
        )
    
    # Просмотр своих заявок
    elif data == "my_requests":
        requests = get_user_requests(user_id)
        
        if not requests:
            await query.edit_message_text(
                "📭 У вас пока нет заявок.",
                reply_markup=get_back_to_main_button(),
                parse_mode="Markdown"
            )
            return
        
        text = "📋 **Ваши заявки:**\n\n"
        for req in requests:
            text += (
                f"🔹 **Заявка №{req['id']}** от {req['created_at'][:10]}\n"
                f"   Проблема: {req['problem_type']}\n"
                f"   Статус: {get_status_emoji(req['status'])} {req['status']}\n"
                f"   Описание: {req['problem_description'][:50]}...\n\n"
            )
        
        await query.edit_message_text(
            text,
            reply_markup=get_back_to_main_button(),
            parse_mode="Markdown"
        )
    
    # Контакты
    elif data == "contacts":
        text = (
            "📞 **Контакты сервиса:**\n\n"
            "📱 **Телефон:** +7 (913) 735-24-65\n"
            "📧 **Email:** doc.cyber@yandex.ru\n"
            "📍 **Адрес:** г. Обь, ул. Октябрьская, 5\n\n"
            "🕐 **График работы:**\n"
            "Пн-Пт: 9:00 - 20:00\n"
            "Сб-Вс: 10:00 - 18:00"
        )
        await query.edit_message_text(
            text,
            reply_markup=get_back_to_main_button(),
            parse_mode="Markdown"
        )
    
    # Цены
    elif data == "prices":
        text = (
            "💰 **Наши цены:**\n\n"
            "🆓 **Диагностика** - БЕСПЛАТНО\n\n"
            "🛠️ **Аппаратный ремонт:**\n"
            "• Замена комплектующих ПК: от 300 ₽\n"
            "• Замена комплектующих ноутбуков: от 2000 ₽\n\n"
            "🖨️ **Оргтехника:**\n"
            "• Обслуживание оргтехники: от 2000 ₽\n\n"
            "💿 **Программное обеспечение:**\n"
            "• Установка Windows: от 700 ₽\n"
            "• Удаление вирусов: от 1000 ₽\n\n"
            "🌡️ **Перегрев:**\n"
            "• Замена термопасты: от 800 ₽\n"
            "• Чистка системы охлаждения: от 1000 ₽"
        )
        await query.edit_message_text(
            text,
            reply_markup=get_back_to_main_button(),
            parse_mode="Markdown"
        )
    
    # Выбор проблемы
    elif data.startswith("problem_"):
        problem_type = data.replace("problem_", "")
        problem_names = {
            "not_starting": "💻 Не включается",
            "slow": "🖥️ Медленно работает",
            "overheating": "🌡️ Перегревается",
            "office": "🖨️ Проблема с оргтехникой",
            "software": "💿 Проблема с ПО",
            "internet": "🌐 Нет интернета",
            "other": "❓ Другая проблема"
        }
        
        problem_name = problem_names.get(problem_type, "❓ Другая проблема")
        
        user_states[user_id] = {
            "step": "enter_description",
            "problem_type": problem_type,
            "problem_name": problem_name
        }
        
        await query.edit_message_text(
            f"✅ Выбрано: **{problem_name}**\n\n"
            "📝 **Опишите проблему подробно:**\n"
            "Напишите сообщение с описанием...",
            parse_mode="Markdown"
        )

# ========== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (создание заявки)"""
    user_id = update.effective_user.id
    user = update.effective_user
    message_text = update.message.text
    
    # Проверяем, есть ли пользователь в процессе создания заявки
    if user_id not in user_states:
        await update.message.reply_text(
            "Используйте кнопки меню для навигации.",
            reply_markup=get_main_menu()
        )
        return
    
    current_step = user_states[user_id].get("step")
    
    # Шаг 1: Ввод описания
    if current_step == "enter_description":
        user_states[user_id]["description"] = message_text
        user_states[user_id]["step"] = "enter_phone"
        
        await update.message.reply_text(
            "📝 **Описание сохранено!**\n\n"
            "📞 **Введите номер телефона:**\n"
            "Например: +7 (913) 735-24-65",
            parse_mode="Markdown"
        )
    
    # Шаг 2: Ввод телефона
    elif current_step == "enter_phone":
        if not validate_phone(message_text):
            await update.message.reply_text(
                "❌ **Неверный формат номера**\n\n"
                "Введите номер еще раз:",
                parse_mode="Markdown"
            )
            return
        
        # Сохраняем заявку в БД
        try:
            request_id = add_request(
                user_id=user_id,
                username=user.username,
                client_name=user.full_name,
                phone=message_text,
                problem_type=user_states[user_id]["problem_name"],
                problem_description=user_states[user_id]["description"]
            )
            
            # Отправляем подтверждение пользователю
            await update.message.reply_text(
                f"✅ **Заявка №{request_id} принята!**\n\n"
                f"Наш специалист свяжется с вами в ближайшее время.",
                parse_mode="Markdown"
            )
            
            # Отправляем уведомление админу
            if ADMIN_ID:
                admin_text = (
                    f"🎯 **НОВАЯ ЗАЯВКА №{request_id}**\n\n"
                    f"👤 **Клиент:** {user.full_name}\n"
                    f"📞 **Телефон:** {message_text}\n"
                    f"🆔 **Username:** @{user.username or 'нет'}\n"
                    f"🔧 **Проблема:** {user_states[user_id]['problem_name']}\n"
                    f"📝 **Описание:** {user_states[user_id]['description']}\n"
                    f"📅 **Время:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=admin_text,
                    parse_mode="Markdown"
                )
            
            # Очищаем состояние
            del user_states[user_id]
            
        except Exception as e:
            logger.error(f"Ошибка сохранения заявки: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=get_main_menu()
            )

# ========== ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ (ТОЛЬКО КНОПКИ) ==========
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех кнопок админ-панели"""
    query = update.callback_query
    await query.answer()
    
    # Проверка прав администратора
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    data = query.data
    
    # Главное меню админа
    if data == "admin_main":
        await query.edit_message_text(
            "🔐 **Панель администратора**\n\nВыберите действие:",
            reply_markup=get_admin_main_menu(),
            parse_mode="Markdown"
        )
    
    # Статистика
    elif data == "admin_stats":
        stats = get_requests_stats()
        text = (
            f"📊 **Статистика заявок**\n\n"
            f"📌 Всего заявок: **{stats['total']}**\n"
            f"📅 За сегодня: **{stats['today']}**\n\n"
            f"🆕 Новых: **{stats['by_status'].get('Новая', 0)}**\n"
            f"⚙️ В работе: **{stats['by_status'].get('В работе', 0)}**\n"
            f"✅ Готово: **{stats['by_status'].get('Готово', 0)}**"
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_main")
            ]]),
            parse_mode="Markdown"
        )
    
    # Показать все заявки
    elif data == "admin_all":
        await show_admin_requests_page(query, 0, "all")
    
    # Показать заявки по статусу
    elif data.startswith("admin_status_") and "_page_" not in data:
        status = data.replace("admin_status_", "")
        await show_admin_requests_page(query, 0, "status", status)
    
    # Пагинация для всех заявок
    elif data.startswith("admin_all_page_"):
        page = int(data.split("_")[-1])
        await show_admin_requests_page(query, page, "all")
    
    # Пагинация для заявок по статусу
    elif data.startswith("admin_status_") and "_page_" in data:
        parts = data.split("_page_")
        status = parts[0].replace("admin_status_", "")
        page = int(parts[1])
        await show_admin_requests_page(query, page, "status", status)
    
    # Управление конкретной заявкой
    elif data.startswith("admin_manage_"):
        request_id = int(data.split("_")[-1])
        request = get_request_by_id(request_id)
        
        if not request:
            await query.edit_message_text("❌ Заявка не найдена")
            return
        
        text = (
            f"🔧 **Управление заявкой №{request['id']}**\n\n"
            f"👤 **Клиент:** {request['client_name']}\n"
            f"📞 **Телефон:** {request['phone']}\n"
            f"🆔 **Username:** @{request['username'] or 'нет'}\n"
            f"🔧 **Проблема:** {request['problem_type']}\n"
            f"📝 **Описание:** {request['problem_description']}\n"
            f"📅 **Создана:** {request['created_at']}\n"
            f"🔹 **Текущий статус:** {get_status_emoji(request['status'])} {request['status']}"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=get_admin_request_management_keyboard(request_id, request['status']),
            parse_mode="Markdown"
        )
    
    # Изменение статуса
    elif data.startswith("admin_status_"):
        parts = data.split("_")
        request_id = int(parts[2])
        new_status = parts[3]
        
        # Обновляем статус
        update_request_status(request_id, new_status)
        
        # Уведомляем клиента
        request = get_request_by_id(request_id)
        if request:
            try:
                await context.bot.send_message(
                    request['user_id'],
                    f"{get_status_emoji(new_status)} **Статус заявки №{request_id} изменен!**\n\n"
                    f"Новый статус: **{new_status}**",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить клиента: {e}")
        
        # Возвращаемся к управлению заявкой
        query.data = f"admin_manage_{request_id}"
        await admin_button_handler(update, context)
    
    # Контакты клиента
    elif data.startswith("admin_contact_"):
        request_id = int(data.split("_")[-1])
        request = get_request_by_id(request_id)
        
        if request:
            text = (
                f"📞 **Контакты клиента**\n\n"
                f"👤 **Имя:** {request['client_name']}\n"
                f"📱 **Телефон:** {request['phone']}\n"
                f"🆔 **Telegram ID:** `{request['user_id']}`\n"
                f"📱 **Username:** @{request['username'] or 'не указан'}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Написать", url=f"tg://user?id={request['user_id']}")],
                [InlineKeyboardButton("◀️ Назад", callback_data=f"admin_manage_{request_id}")]
            ])
            
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
    
    # Удаление заявки (подтверждение)
    elif data.startswith("admin_delete_"):
        request_id = int(data.split("_")[-1])
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да", callback_data=f"admin_confirm_delete_{request_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"admin_manage_{request_id}")
            ]
        ])
        
        await query.edit_message_text(
            f"⚠️ **Удалить заявку №{request_id}?**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    # Подтверждение удаления
    elif data.startswith("admin_confirm_delete_"):
        request_id = int(data.split("_")[-1])
        delete_request(request_id)
        
        await query.edit_message_text(
            f"✅ Заявка №{request_id} удалена.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ К списку", callback_data="admin_all")
            ]])
        )
    
    # Назад к списку
    elif data == "admin_back_to_list":
        query.data = "admin_all"
        await admin_button_handler(update, context)
    
    # Заглушка для некликабельных кнопок
    elif data == "ignore":
        pass

async def show_admin_requests_page(query, page, filter_type, status=None):
    """Отображение страницы с заявками для админа"""
    # Получаем заявки
    if filter_type == "all":
        all_requests = get_all_requests()
        prefix = "admin_all"
    else:
        all_requests = get_requests_by_status(status)
        prefix = f"admin_status_{status}"
    
    if not all_requests:
        await query.edit_message_text(
            "📭 Заявок не найдено",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_main")
            ]])
        )
        return
    
    # Пагинация
    total_pages = (len(all_requests) + REQUESTS_PER_PAGE - 1) // REQUESTS_PER_PAGE
    start = page * REQUESTS_PER_PAGE
    end = start + REQUESTS_PER_PAGE
    requests_page = all_requests[start:end]
    
    # Формируем текст
    text = f"📋 **Список заявок** (стр. {page+1}/{total_pages})\n\n"
    
    for req in requests_page:
        text += (
            f"{get_status_emoji(req['status'])} **№{req['id']}** | {req['created_at'][:16]}\n"
            f"👤 {req['client_name']}\n"
            f"📞 {req['phone']}\n"
            f"📝 {req['problem_description'][:50]}...\n\n"
        )
    
    # Создаем клавиатуру
    buttons = []
    
    # Кнопки для каждой заявки
    for req in requests_page:
        buttons.append([InlineKeyboardButton(
            f"🔧 Управлять №{req['id']}",
            callback_data=f"admin_manage_{req['id']}"
        )])
    
    # Кнопки пагинации
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_page_{page+1}"))
    buttons.append(nav_row)
    
    # Кнопка в главное меню
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="admin_main")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск бота"""
    # Инициализация БД
    init_database()
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_command))
    
    # Обработчик для клиентских кнопок (все, кроме admin_*)
    application.add_handler(CallbackQueryHandler(
        button_handler, 
        pattern="^(?!admin_).*"  # Все что не начинается с admin_
    ))
    
    # Обработчик для админских кнопок
    application.add_handler(CallbackQueryHandler(
        admin_button_handler,
        pattern="^admin_.*"
    ))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        message_handler
    ))
    
    # Запуск
    logger.info("🚀 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
