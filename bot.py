#!/usr/bin/env python3

import logging
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# Загружаем переменные из .env файла
load_dotenv()

# Получаем настройки из окружения
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Преобразуем ADMIN_ID в число, так как из .env приходит строка
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)

# ========== НАСТРОЙКИ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверка наличия обязательных настроек
if not TOKEN:
    logger.error("❌ BOT_TOKEN не найден! Проверьте файл .env")
    raise ValueError("BOT_TOKEN не настроен")

if not ADMIN_ID:
    logger.warning("⚠️ ADMIN_ID не настроен! Заявки не будут отправляться администратору")

# ========= ХРАНЕНИЕ ДАННЫХ ==========
user_data = {}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_phone(phone):
    """Простая проверка номера телефона"""
    # Удаляем все кроме цифр
    digits = ''.join(filter(str.isdigit, phone))
    # Проверяем длину (10-11 цифр для российских номеров)
    return 10 <= len(digits) <= 11

# ========== КНОПКИ ==========
def get_main_menu():
    """Главное меню"""
    buttons = [
        [InlineKeyboardButton("🆘 Создать заявкуxaxa", callback_data="create")],
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts")],
        [InlineKeyboardButton("💰 Цены", callback_data="prices")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_problems_menu():
    """Меню выбора проблемы (расширенное)"""
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

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    text = f"""👋 Здравствуйте, {user.first_name}!

🛠️ *Сервисный центр по ремонту и обслуживанию компьютеров*

Мы поможем с любой проблемой:
• Диагностика - бесплатно
• Быстрый ремонт
• Широкий спектр услуг

Выберите действие:"""
    
    await update.message.reply_text(
        text, 
        reply_markup=get_main_menu(), 
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "📋 *Доступные команды:*\n"
        "/start - Начать работу с ботом\n"
        "/help - Получить справку\n\n"
        "Используйте кнопки меню для навигации.",
        parse_mode="Markdown"
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "back" or data == "menu":
        # Возврат в главное меню
        await query.edit_message_text(
            "📋 *Главное меню*\n\nВыберите нужное действие:",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )
    
    elif data == "create":
        # Начать создание заявки
        user_data[user_id] = {"step": "select_problem"}
        await query.edit_message_text(
            "🛠️ *Выберите тип проблемы:*\n\n"
            "Пожалуйста, укажите наиболее подходящую категорию:",
            reply_markup=get_problems_menu(),
            parse_mode="Markdown"
        )
    
    elif data.startswith("problem_"):
        # Пользователь выбрал проблему
        problem_type = data.replace("problem_", "")
        
        # Определяем название проблемы (расширенный список)
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
        
        # Сохраняем данные и переходим к запросу описания (ИЗМЕНЕНО: теперь сначала описание)
        user_data[user_id] = {
            "step": "enter_description",  # ИЗМЕНЕНО: было "enter_phone", стало "enter_description"
            "problem_type": problem_type,
            "problem_name": problem_name
        }
        
        await query.edit_message_text(
            f"✅ Выбрано: *{problem_name}*\n\n"
            "📝 *Теперь подробно опишите проблему:*\n\n"  # ИЗМЕНЕНО: теперь запрашиваем описание
            "Напишите сообщение с описанием, например:\n"
            "• Когда началась проблема\n"
            "• Что уже пробовали сделать\n"
            "• Особые детали\n\n"
            "✏️ *Введите ваше описание:*",
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]),
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
                [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
            ]),
            parse_mode="Markdown"
        )

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    user = update.effective_user
    message_text = update.message.text
    
    # Проверяем, находится ли пользователь в процессе создания заявки
    if user_id in user_data:
        current_step = user_data[user_id].get("step")
        
        # ИЗМЕНЕНО: теперь сначала описание, потом телефон
        # Шаг 1: Ввод описания проблемы (НОВЫЙ ПЕРВЫЙ ШАГ)
        if current_step == "enter_description":
            # Сохраняем описание
            user_data[user_id]["description"] = message_text
            # Меняем шаг на запрос телефона
            user_data[user_id]["step"] = "enter_phone"
            
            # Переходим к запросу номера телефона
            await update.message.reply_text(
                f"📝 *Описание сохранено!*\n\n"
                "📞 *Теперь укажите ваш номер телефона*\n\n"
                "Напишите номер в формате:\n"
                "• +7 (XXX) XXX-XX-XX\n"
                "• 8 (XXX) XXX-XX-XX\n"
                "• или просто 10-11 цифр\n\n"
                "✏️ *Введите номер телефона:*",
                parse_mode="Markdown"
            )
        
        # Шаг 2: Ввод номера телефона (НОВЫЙ ВТОРОЙ ШАГ)
        elif current_step == "enter_phone":
            # Проверяем корректность номера
            if not validate_phone(message_text):
                await update.message.reply_text(
                    "❌ *Неверный формат номера*\n\n"
                    "Пожалуйста, введите корректный номер телефона:\n"
                    "• +7 (XXX) XXX-XX-XX\n"
                    "• 8 (XXX) XXX-XX-XX\n"
                    "• или просто 10-11 цифр\n\n"
                    "✏️ *Попробуйте снова:*",
                    parse_mode="Markdown"
                )
                return
            
            # Сохраняем номер телефона
            user_data[user_id]["phone"] = message_text
            # Получаем сохраненное ранее описание
            problem_info = user_data[user_id]
            problem_description = problem_info.get('description', 'Не указано')
            
            try:
                # Формируем заявку для пользователя
                user_request_text = f"""📋 *ВАША ЗАЯВКА ПРИНЯТА*

🔧 *Проблема:* {problem_info.get('problem_name', 'Не указана')}
📝 *Описание:* {problem_description}

👤 *Ваши данные:*
• Имя: {user.full_name}
• Username: @{user.username or 'не указан'}
• Телефон: {message_text}
• ID: {user_id}

📅 *Время создания:* {datetime.now().strftime('%d.%m.%Y %H:%M')}

✅ *Заявка №{user_id % 10000} принята!*
Наш специалист свяжется с вами в ближайшее время.

📞 *Контакты для срочных вопросов:*
+7 (913) 735-24-65"""
                
                # Формируем заявку для администратора (с телефоном и описанием)
                admin_request_text = f"""🎯 *НОВАЯ ЗАЯВКА НА РЕМОНТ!*

👤 *КЛИЕНТ:*
• Имя: {user.full_name}
• Username: @{user.username or 'нет'}
• Телефон: {message_text}
• ID: {user_id}

🔧 *ПРОБЛЕМА:* {problem_info.get('problem_name', 'Не указана')}
📝 *ОПИСАНИЕ:*
{problem_description}

📅 *ВРЕМЯ:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
🆔 *НОМЕР ЗАЯВКИ:* {user_id % 10000}

━━━━━━━━━━━━━━━━━━━━━━
⚠️ *ТРЕБУЕТСЯ ОБРАБОТКА*"""
                
                # Шаг 1: Отправляем подтверждение пользователю
                await update.message.reply_text(
                    "⏳ *Обрабатываю вашу заявку...*",
                    parse_mode="Markdown"
                )
                
                # Небольшая пауза для лучшего UX
                await asyncio.sleep(1)
                
                # Шаг 2: Отправляем детали пользователю
                await update.message.reply_text(
                    user_request_text,
                    parse_mode="Markdown"
                )
                
                # Шаг 3: Отправляем заявку администратору
                if ADMIN_ID and ADMIN_ID != 123456789:
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=admin_request_text,
                            parse_mode="Markdown"
                        )
                        logger.info(f"✅ Заявка отправлена администратору {ADMIN_ID}")
                    except Exception as admin_error:
                        logger.error(f"❌ Ошибка отправки администратору: {admin_error}")
                        # Продолжаем работу даже если не удалось отправить админу
                else:
                    logger.warning("⚠️ ADMIN_ID не настроен! Заявка не отправлена администратору.")
                
                # Шаг 4: Показываем финальное сообщение с меню
                await update.message.reply_text(
                    "✅ *Заявка успешно создана и отправлена!*\n\n"
                    "📱 *Что дальше?*\n"
                    "1. Наш специалист получил вашу заявку.\n"
                    "2. Он свяжется с вами по указанному телефону в ближайшее время.\n"
                    "3. Если вопрос срочный, позвоните нам по телефону +7 (913) 735-24-65.\n\n"
                    "⬇️ *Вернуться в главное меню:*",
                    reply_markup=get_main_menu(),
                    parse_mode="Markdown"
                )
                
                # Очищаем данные пользователя после завершения заявки
                # Можно закомментировать, если нужно хранить историю, но лучше очищать
                del user_data[user_id]
                
            except Exception as e:
                logger.error(f"❌ Ошибка при создании заявки: {e}")
                await update.message.reply_text(
                    "❌ *Произошла ошибка при создании заявки*\n\n"
                    "Пожалуйста, попробуйте позже или свяжитесь с нами по телефону.",
                    reply_markup=get_main_menu(),
                    parse_mode="Markdown"
                )
    else:
        # Если пользователь не в процессе создания заявки
        await update.message.reply_text(
            "Используйте /start для начала работы с ботом",
            reply_markup=get_main_menu()
        )

# ========== ЗАПУСК БОТА ==========
async def post_init(application: Application):
    """Действия после инициализации бота"""
    logger.info("🚀 Бот запущен и готов к работе!")

def main():
    """Главная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Запускаем бота
    logger.info("🔄 Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
