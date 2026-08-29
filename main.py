import os
import telebot
from telebot import types
import sqlite3

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get('BOT_TOKEN') # Теперь токен берется из настроек хостинга
ADMIN_IDS = [1659141886, 1243314006, 7023363751]
MAX_ACCOUNTS = 2
bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('fazan_server.db')
    c = conn.cursor()
    # Таблица лимитов пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (tg_id INTEGER PRIMARY KEY, whitelist_count INTEGER DEFAULT 0)''')
    # Таблица самих заявок
    c.execute('''CREATE TABLE IF NOT EXISTS wl_requests 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nickname TEXT, tg_user_id INTEGER, status TEXT DEFAULT 'pending')''')
    # Таблица для хранения сообщений админов (чтобы менять их у всех сразу)
    c.execute('''CREATE TABLE IF NOT EXISTS admin_msgs 
                 (request_id INTEGER, admin_id INTEGER, message_id INTEGER)''')
    conn.commit()
    conn.close()

def get_whitelist_count(tg_id):
    conn = sqlite3.connect('fazan_server.db')
    c = conn.cursor()
    c.execute("SELECT whitelist_count FROM users WHERE tg_id = ?", (tg_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def increment_whitelist_count(tg_id):
    conn = sqlite3.connect('fazan_server.db')
    c = conn.cursor()
    count = get_whitelist_count(tg_id)
    if count == 0:
        c.execute("INSERT INTO users (tg_id, whitelist_count) VALUES (?, 1)", (tg_id,))
    else:
        c.execute("UPDATE users SET whitelist_count = whitelist_count + 1 WHERE tg_id = ?", (tg_id,))
    conn.commit()
    conn.close()

# --- СЛОВАРИ СОСТОЯНИЙ ---
user_states = {} 

# --- КЛАВИАТУРА МЕНЮ ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📝 Добавиться в белый список")
    btn2 = types.KeyboardButton("💬 Поддержка")
    markup.add(btn1, btn2)
    return markup

# --- ЛОГИКА БОТА ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_states[message.chat.id] = None
    bot.send_message(
        message.chat.id, 
        "Привет! Добро пожаловать в бота Fazan Server. Выберите действие:", 
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "📝 Добавиться в белый список")
def whitelist_request(message):
    tg_id = message.chat.id
    count = get_whitelist_count(tg_id)
    
    if count >= MAX_ACCOUNTS:
        bot.send_message(tg_id, f"❌ Вы уже добавили максимальное количество аккаунтов ({MAX_ACCOUNTS}).")
        return
    
    user_states[tg_id] = 'waiting_for_nick'
    bot.send_message(tg_id, "Введите ваш никнейм в Minecraft (отмена - /start):", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "💬 Поддержка")
def support_request(message):
    tg_id = message.chat.id
    user_states[tg_id] = 'support_mode'
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Завершить диалог"))
    
    bot.send_message(tg_id, "Режим поддержки включен. Опишите вашу проблему, и администратор ответит вам здесь.", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "❌ Завершить диалог")
def end_support(message):
    user_states[message.chat.id] = None
    bot.send_message(message.chat.id, "Диалог завершен.", reply_markup=get_main_menu())

# Обработка текста
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    tg_id = message.chat.id
    state = user_states.get(tg_id)
    
    # 1. Ответ админа в поддержке
    if tg_id in ADMIN_IDS and message.reply_to_message:
        reply_text = message.reply_to_message.text
        if reply_text and "ID:" in reply_text:
            try:
                user_id_str = reply_text.split("ID: ")[1].split("\n")[0]
                target_user_id = int(user_id_str)
                bot.send_message(target_user_id, f"👨‍💻 **Ответ администратора:**\n{message.text}", parse_mode="Markdown")
                bot.reply_to(message, "Ответ отправлен игроку.")
            except Exception:
                bot.reply_to(message, "Ошибка при отправке.")
        return

    # 2. Ввод никнейма для белого списка
    if state == 'waiting_for_nick':
        nickname = message.text.strip()
        increment_whitelist_count(tg_id)
        user_states[tg_id] = None
        
        bot.send_message(tg_id, f"✅ Никнейм `{nickname}` отправлен на проверку администраторам!", parse_mode="Markdown", reply_markup=get_main_menu())
        
        # Записываем заявку в БД, чтобы получить её ID
        conn = sqlite3.connect('fazan_server.db')
        c = conn.cursor()
        c.execute("INSERT INTO wl_requests (nickname, tg_user_id) VALUES (?, ?)", (nickname, tg_id))
        request_id = c.lastrowid
        conn.commit()

        # Создаем инлайн-кнопку
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("✅ Добавить", callback_data=f"wl_approve_{request_id}")
        markup.add(btn)

        # Отправляем админам и сохраняем ID сообщений
        for admin in ADMIN_IDS:
            try:
                username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {tg_id}"
                msg = bot.send_message(admin, f"🚨 **Новая заявка в Whitelist!**\nНикнейм: `{nickname}`\nОт: {username}", parse_mode="Markdown", reply_markup=markup)
                c.execute("INSERT INTO admin_msgs (request_id, admin_id, message_id) VALUES (?, ?, ?)", (request_id, admin, msg.message_id))
            except:
                pass
        
        conn.commit()
        conn.close()
        return

    # 3. Режим поддержки
    if state == 'support_mode':
        for admin in ADMIN_IDS:
            try:
                username = f"@{message.from_user.username}" if message.from_user.username else "Без юзернейма"
                support_msg = f"📩 **Запрос в поддержку**\nID: {tg_id}\nОт: {username}\n\nТекст: {message.text}"
                bot.send_message(admin, support_msg)
            except:
                pass
        return

    bot.send_message(tg_id, "Пожалуйста, используйте кнопки меню.", reply_markup=get_main_menu())

# --- ОБРАБОТКА НАЖАТИЯ КНОПОК АДМИНАМИ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wl_approve_'))
def handle_whitelist_approval(call):
    request_id = int(call.data.split('_')[2])
    
    conn = sqlite3.connect('fazan_server.db')
    c = conn.cursor()
    
    # Проверяем статус заявки
    c.execute("SELECT status, nickname, tg_user_id FROM wl_requests WHERE id = ?", (request_id,))
    request_data = c.fetchone()
    
    if not request_data:
        bot.answer_callback_query(call.id, "Заявка не найдена.")
        conn.close()
        return
        
    status, nickname, tg_user_id = request_data
    
    if status == 'approved':
        bot.answer_callback_query(call.id, "Эта заявка уже обработана другим администратором!", show_alert=True)
        conn.close()
        return
        
    # Помечаем заявку как обработанную
    c.execute("UPDATE wl_requests SET status = 'approved' WHERE id = ?", (request_id,))
    
    # Получаем все сообщения админов с этой заявкой
    c.execute("SELECT admin_id, message_id FROM admin_msgs WHERE request_id = ?", (request_id,))
    admin_messages = c.fetchall()
    
    conn.commit()
    conn.close()
    
    admin_name = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
    
    # Редактируем сообщение У ВСЕХ админов
    for admin_id, message_id in admin_messages:
        try:
            bot.edit_message_text(
                chat_id=admin_id,
                message_id=message_id,
                text=f"✅ **Заявка обработана!**\nНикнейм: `{nickname}`\nДобавил: {admin_name}",
                parse_mode="Markdown",
                reply_markup=None # Убирает инлайн-кнопку
            )
        except Exception:
            pass # Если админ удалил сообщение, просто игнорируем ошибку
            
    # Уведомляем игрока, что его приняли
    try:
        bot.send_message(tg_user_id, f"🎉 Ваш никнейм `{nickname}` успешно добавлен в белый список администратором!")
    except:
        pass

    # Уведомление для того админа, который нажал кнопку (появляется сверху экрана)
    bot.answer_callback_query(call.id, f"Никнейм {nickname} добавлен! Все админы оповещены.")

if __name__ == '__main__':
    init_db()
    print("Бот Fazan Server запущен...")
    bot.infinity_polling()
