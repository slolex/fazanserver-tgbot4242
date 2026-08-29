import os
import requests
import telebot
from telebot import types
import sqlite3

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get('BOT_TOKEN') # Токен берется из переменных окружения хостинга
ADMIN_IDS = [1659141886, 1243314006, 7023363751]
MAX_ACCOUNTS = 2 

bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('fazan_server.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (tg_id INTEGER PRIMARY KEY, whitelist_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS wl_requests 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nickname TEXT, tg_user_id INTEGER, status TEXT DEFAULT 'pending')''')
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
active_chats = {} # Формат: {admin_id: user_id}

def get_available_admins():
    # Возвращает список админов, которые сейчас НЕ находятся в чате
    return [admin for admin in ADMIN_IDS if admin not in active_chats]

# --- КЛАВИАТУРЫ ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📝 Добавиться в белый список"))
    markup.add(types.KeyboardButton("💬 Поддержка"), types.KeyboardButton("⬇️ Скачать лаунчер"))
    return markup

def get_cancel_menu(text="❌ Завершить диалог"):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton(text))
    return markup

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_states[message.chat.id] = None
    bot.send_message(
        message.chat.id, 
        "Привет! Добро пожаловать в бота Fazan Server. Выберите действие:", 
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "⬇️ Скачать лаунчер")
def send_launcher(message):
    tg_id = message.chat.id
    direct_link = "https://www.dropbox.com/scl/fi/v62ngxh27wp7lcaz514qv/FazanLauncher.exe?rlkey=1bqd6ht7lejp9vip1dyq0io3x&st=8s0y3quf&dl=1"
    
    bot.send_message(tg_id, "⏳ Загружаю лаунчер, это займет несколько секунд...")
    
    try:
        # 1. Бот скачивает файл с Dropbox в свою память
        response = requests.get(direct_link, timeout=30)
        response.raise_for_status()
        
        # 2. Бот отправляет скачанный файл в Telegram, передав имя файла и байты
        bot.send_document(
            tg_id, 
            document=('FazanLauncher.exe', response.content), 
            caption="🎮 Ваш лаунчер Fazan Server!"
        )
    except Exception as e:
        bot.send_message(
            tg_id, 
            f"📥 Скачать лаунчер:\n{direct_link.replace('dl=1', 'dl=0')}"
        )

@bot.message_handler(func=lambda message: message.text == "📝 Добавиться в белый список")
def whitelist_request(message):
    tg_id = message.chat.id
    
    if get_whitelist_count(tg_id) >= MAX_ACCOUNTS:
        bot.send_message(tg_id, f"❌ Вы уже добавили максимальное количество аккаунтов ({MAX_ACCOUNTS}).")
        return
    
    user_states[tg_id] = 'waiting_for_nick'
    bot.send_message(tg_id, "Введите ваш никнейм в Minecraft (отмена - /start):", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == "💬 Поддержка")
def support_request(message):
    tg_id = message.chat.id
    user_states[tg_id] = 'support_mode'
    bot.send_message(tg_id, "Режим поддержки включен. Опишите вашу проблему:", reply_markup=get_cancel_menu("❌ Завершить диалог"))

# --- ЗАВЕРШЕНИЕ ДИАЛОГОВ ---
@bot.message_handler(func=lambda message: message.text == "❌ Завершить диалог")
def end_support_user(message):
    tg_id = message.chat.id
    user_states[tg_id] = None
    
    # Отключаем админа, если он общался с этим игроком
    admin_to_free = None
    for a_id, u_id in active_chats.items():
        if u_id == tg_id:
            admin_to_free = a_id
            break
            
    if admin_to_free:
        del active_chats[admin_to_free]
        bot.send_message(admin_to_free, "Игрок покинул чат. Вы возвращены в обычный режим, уведомления включены.", reply_markup=types.ReplyKeyboardRemove())
        
    bot.send_message(tg_id, "Вы вышли из режима поддержки.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == "❌ Завершить чат")
def end_support_admin(message):
    tg_id = message.chat.id
    if tg_id in active_chats:
        target_user = active_chats[tg_id]
        del active_chats[tg_id]
        
        bot.send_message(tg_id, "✅ Чат завершен. Уведомления о заявках снова включены.", reply_markup=types.ReplyKeyboardRemove())
        bot.send_message(target_user, "👨‍💻 Администратор завершил диалог. Вы можете написать новый вопрос или выйти.", reply_markup=get_cancel_menu("❌ Завершить диалог"))

# --- ОБРАБОТКА ТЕКСТА ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    tg_id = message.chat.id
    state = user_states.get(tg_id)
    
    # 1. Если пишет АДМИН в режиме чата
    if tg_id in active_chats:
        target_user = active_chats[tg_id]
        try:
            bot.send_message(target_user, f"👨‍💻 {message.text}")
        except:
            bot.send_message(tg_id, "❌ Не удалось отправить сообщение. Возможно, игрок заблокировал бота.")
        return

    # 2. Ввод никнейма для белого списка
    if state == 'waiting_for_nick':
        nickname = message.text.strip()
        increment_whitelist_count(tg_id)
        user_states[tg_id] = None
        
        bot.send_message(tg_id, f"✅ Никнейм `{nickname}` отправлен на проверку администраторам!", parse_mode="Markdown", reply_markup=get_main_menu())
        
        conn = sqlite3.connect('fazan_server.db')
        c = conn.cursor()
        c.execute("INSERT INTO wl_requests (nickname, tg_user_id) VALUES (?, ?)", (nickname, tg_id))
        request_id = c.lastrowid

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Добавить", callback_data=f"wl_{request_id}"))

        for admin in get_available_admins():
            try:
                msg = bot.send_message(admin, f"🚨 **Новая заявка!**\nНикнейм: `{nickname}`", parse_mode="Markdown", reply_markup=markup)
                c.execute("INSERT INTO admin_msgs (request_id, admin_id, message_id) VALUES (?, ?, ?)", (request_id, admin, msg.message_id))
            except: pass
        
        conn.commit()
        conn.close()
        return

    # 3. Режим поддержки (игрок пишет)
    if state == 'support_mode':
        current_admin = None
        for a_id, u_id in active_chats.items():
            if u_id == tg_id:
                current_admin = a_id
                break
                
        if current_admin:
            bot.send_message(current_admin, f"👤 {message.text}")
        else:
            username = f"@{message.from_user.username}" if message.from_user.username else "Без юзернейма"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💬 Начать чат", callback_data=f"chat_{tg_id}"))
            
            support_msg = f"📩 **Новый запрос (Поддержка)**\nОт: {username}\n\nТекст: {message.text}"
            for admin in get_available_admins():
                try: bot.send_message(admin, support_msg, reply_markup=markup)
                except: pass
        return

    bot.send_message(tg_id, "Пожалуйста, используйте кнопки меню.", reply_markup=get_main_menu())

# --- ОБРАБОТКА ИНЛАЙН КНОПОК АДМИНАМИ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('chat_') or call.data.startswith('wl_'))
def handle_callbacks(call):
    admin_id = call.message.chat.id
    
    # Кнопка "Начать чат"
    if call.data.startswith('chat_'):
        user_id = int(call.data.split('_')[1])
        
        if admin_id in active_chats:
            bot.answer_callback_query(call.id, "Вы уже находитесь в чате!", show_alert=True)
            return
            
        if user_id in active_chats.values():
            bot.answer_callback_query(call.id, "Этого игрока уже забрал другой администратор!", show_alert=True)
            bot.edit_message_reply_markup(admin_id, call.message.message_id, reply_markup=None)
            return
            
        active_chats[admin_id] = user_id
        
        bot.answer_callback_query(call.id, "Вы подключились к чату!")
        bot.edit_message_reply_markup(admin_id, call.message.message_id, reply_markup=None)
        
        bot.send_message(admin_id, "✅ **Вы вошли в чат с игроком.**\nТеперь все ваши сообщения отправляются ему. Уведомления о других заявках скрыты.", parse_mode="Markdown", reply_markup=get_cancel_menu("❌ Завершить чат"))
        
        try: bot.send_message(user_id, "👨‍💻 Администратор подключился к диалогу!")
        except: pass

    # Кнопка "Добавить в Whitelist"
    elif call.data.startswith('wl_'):
        request_id = int(call.data.split('_')[1])
        
        conn = sqlite3.connect('fazan_server.db')
        c = conn.cursor()
        c.execute("SELECT status, nickname, tg_user_id FROM wl_requests WHERE id = ?", (request_id,))
        request_data = c.fetchone()
        
        if not request_data or request_data[0] == 'approved':
            bot.answer_callback_query(call.id, "Уже обработано!", show_alert=True)
            conn.close()
            return
            
        status, nickname, tg_user_id = request_data
        c.execute("UPDATE wl_requests SET status = 'approved' WHERE id = ?", (request_id,))
        c.execute("SELECT admin_id, message_id FROM admin_msgs WHERE request_id = ?", (request_id,))
        admin_messages = c.fetchall()
        conn.commit()
        conn.close()
        
        admin_name = f"@{call.from_user.username}" if call.from_user.username else "Администратор"
        
        for a_id, msg_id in admin_messages:
            try:
                bot.edit_message_text(f"✅ **Заявка обработана!**\nНикнейм: `{nickname}`\nДобавил: {admin_name}", a_id, msg_id, parse_mode="Markdown", reply_markup=None)
            except: pass
                
        try: bot.send_message(tg_user_id, f"🎉 Ваш никнейм `{nickname}` добавлен на сервер!")
        except: pass
        bot.answer_callback_query(call.id, f"{nickname} добавлен!")

if __name__ == '__main__':
    init_db()
    print("Бот Fazan Server запущен...")
    bot.infinity_polling()
