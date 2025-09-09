import asyncio
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.enums import ContentType
import sqlite3
import datetime
from collections import defaultdict

# Bot tokenini kiriting
TOKEN = '8228698744:AAGXRtJs30Pe2ngjdzSYIDLYLbcKbdPgyu4'  # BotFather'dan olingan token
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# SQLite3 uchun datetime.date adapteri
def adapt_date(date):
    return date.isoformat()

def convert_date(s):
    return datetime.date.fromisoformat(s.decode('utf-8') if isinstance(s, bytes) else s)

sqlite3.register_adapter(datetime.date, adapt_date)
sqlite3.register_converter('DATE', convert_date)

# Ma'lumotlar bazasi
conn = sqlite3.connect('anime_bot.db', check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
cursor = conn.cursor()

# Jadvallar yaratish va yangilash
def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS anime (
        code TEXT PRIMARY KEY,
        name TEXT,
        episodes INTEGER
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS episodes (
        code TEXT,
        episode_num INTEGER,
        file_id TEXT,
        caption TEXT,
        PRIMARY KEY (code, episode_num)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        join_date DATE,
        is_subscribed INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        is_active INTEGER DEFAULT 1
    )
    ''')
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'join_date' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN join_date DATE')
    if 'is_subscribed' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN is_subscribed INTEGER DEFAULT 0')

    # Boshlang'ich kanal qo'shish
    cursor.execute('SELECT url FROM channels WHERE url = ?', ('https://t.me/AniRude1',))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO channels (title, url) VALUES (?, ?)', ('AniRude Kodlar', 'https://t.me/AniRude1'))
        conn.commit()

    conn.commit()

# Ma'lumotlar bazasini ishga tushirish
init_db()

# Admin ID (sizning ID)
initial_admin_id = 5668810530
cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (initial_admin_id,))
conn.commit()

# Holatlar va ma'lumotlar
user_states = {}
upload_data = defaultdict(dict)
ADD_ANIME_CODE = 'add_anime_code'
ADD_ANIME_NAME = 'add_anime_name'
ADD_ANIME_EPISODES = 'add_anime_episodes'
ADD_ANIME_UPLOAD = 'add_anime_upload'
DELETE_ANIME = 'delete_anime'
ADD_ADMIN = 'add_admin'
REMOVE_ADMIN = 'remove_admin'
ANIMELAR_CODE = 'animelar_code'
ADD_CHANNEL_TITLE = 'add_channel_title'
ADD_CHANNEL_URL = 'add_channel_url'
REMOVE_CHANNEL = 'remove_channel'

# Yordamchi funksiyalar
def is_admin(user_id):
    cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def add_user(user_id):
    today = datetime.date.today()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)', (user_id, today))
    conn.commit()

def get_stats():
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM anime')
    total_anime = cursor.fetchone()[0]
    today = datetime.date.today()
    month_start = today.replace(day=1)
    cursor.execute('SELECT COUNT(*) FROM users WHERE join_date >= ?', (month_start,))
    monthly_users = cursor.fetchone()[0]
    week_start = today - datetime.timedelta(days=today.weekday())
    cursor.execute('SELECT COUNT(*) FROM users WHERE join_date >= ?', (week_start,))
    weekly_users = cursor.fetchone()[0]
    return total_users, total_anime, monthly_users, weekly_users

def get_admins_list():
    cursor.execute('SELECT user_id FROM admins')
    return [row[0] for row in cursor.fetchall()]

def get_anime_list():
    cursor.execute('SELECT code, name FROM anime')
    return [(row[0], row[1]) for row in cursor.fetchall()]

def get_active_channels():
    cursor.execute('SELECT title, url FROM channels WHERE is_active = 1')
    return cursor.fetchall()

def chunk_buttons(buttons, chunk_size=5):
    return [buttons[i:i + chunk_size] for i in range(0, len(buttons), chunk_size)]

def generate_episode_keyboard(code, current_episode, total_episodes):
    buttons = []
    for i in range(1, total_episodes + 1):
        text = f"{i}" if i != current_episode else f"✅ {i}"
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"episode_{code}_{i}"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=chunk_buttons(buttons))
    return keyboard

@router.message(CommandStart())
async def start_handler(message: types.Message):
    add_user(message.from_user.id)
    cursor.execute('SELECT is_subscribed FROM users WHERE user_id = ?', (message.from_user.id,))
    subscribed = cursor.fetchone()
    subscribed = subscribed[0] if subscribed else 0
    args = message.text.split()
    # Komanda argumentlarini tekshirish (masalan, /start subscribed_<user_id>)
    explicit_subscribed = any(arg.startswith('subscribed_') and int(arg.split('_')[-1]) == message.from_user.id for arg in args[1:] if arg)
    channels = get_active_channels()
    if channels and not subscribed and not explicit_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for title, url in channels:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=title, url=url)])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="✅ Obunani tasdiqlash", callback_data=f"check_subscription_{message.from_user.id}")])
        await message.answer("🇺🇿 <b>Majburiy obuna kanallari:</b>", reply_markup=keyboard, disable_web_page_preview=True)
        return
    if len(args) > 1:
        code = args[1]
        cursor.execute('SELECT * FROM anime WHERE code = ?', (code,))
        if cursor.fetchone():
            await show_anime_episode(message.chat.id, code, 1)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔑 Kod kiritish", callback_data="enter_code")],
                [InlineKeyboardButton(text="📢 Kodlar Kanali", url="https://t.me/AniRude1")],
                [InlineKeyboardButton(text="👨‍💼 Admin bilan bogʻlanish", url="https://t.me/rude_lxz")]
            ])
            await message.answer("❌ Kiritilgan kod topilmadi! To'g'ri kod kiriting.", reply_markup=keyboard)
        return
    username = message.from_user.first_name or "Foydalanuvchi"
    greeting = f"🇺🇿 <b>Assalomu aleykum, {username}!</b> 🎬\n\nBu botda hamma turdagi animelar mavjud. Iltimos, anime kodini kiriting.\n\n📢 Kodlar kanali: <a href='https://t.me/AniRude1'>AniRude Kodlar</a> yoki admin bilan bog'laning!"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Kod kiritish", callback_data="enter_code")],
        [InlineKeyboardButton(text="📢 Kodlar Kanali", url="https://t.me/AniRude1")],
        [InlineKeyboardButton(text="👨‍💼 Admin bilan bogʻlanish", url="https://t.me/rude_lxz")]
    ])
    await message.answer(greeting, reply_markup=keyboard, disable_web_page_preview=True)

@router.callback_query(F.data.startswith("check_subscription_"))
async def check_subscription(call: types.CallbackQuery):
    user_id = int(call.data.split('_')[-1])
    if user_id != call.from_user.id:
        await call.answer("Bu tugma siz uchun emas!", show_alert=True)
        return
    channels = get_active_channels()
    if not channels:
        await call.answer("Kanal ro'yxati bo'sh!", show_alert=True)
        return
    user_member = True
    for _, url in channels:
        channel_username = url.replace('https://t.me/', '@')
        try:
            member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                user_member = False
                break
        except Exception as e:
            print(f"Obuna tekshiruvi xatosi: {e}")  # Debugging uchun
            user_member = False
            break
    if user_member:
        await call.message.edit_text("🇺🇿 <b>Obuna tasdiqlandi!</b>", reply_markup=None)
        cursor.execute('UPDATE users SET is_subscribed = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        args = [f"subscribed_{user_id}"]
        code = args[1] if len(args) > 1 else None
        if code:
            cursor.execute('SELECT * FROM anime WHERE code = ?', (code,))
            if cursor.fetchone():
                await show_anime_episode(call.message.chat.id, code, 1)
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔑 Kod kiritish", callback_data="enter_code")],
                    [InlineKeyboardButton(text="📢 Kodlar Kanali", url="https://t.me/AniRude1")],
                    [InlineKeyboardButton(text="👨‍💼 Admin bilan bogʻlanish", url="https://t.me/rude_lxz")]
                ])
                await bot.send_message(call.message.chat.id, "❌ Kiritilgan kod topilmadi! To'g'ri kod kiriting.", reply_markup=keyboard)
        else:
            username = call.from_user.first_name or "Foydalanuvchi"
            greeting = f"🇺🇿 <b>Assalomu aleykum, {username}!</b> 🎬\n\nBu botda hamma turdagi animelar mavjud. Iltimos, anime kodini kiriting.\n\n📢 Kodlar kanali: <a href='https://t.me/AniRude1'>AniRude Kodlar</a> yoki admin bilan bog'laning!"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔑 Kod kiritish", callback_data="enter_code")],
                [InlineKeyboardButton(text="📢 Kodlar Kanali", url="https://t.me/AniRude1")],
                [InlineKeyboardButton(text="👨‍💼 Admin bilan bogʻlanish", url="https://t.me/rude_lxz")]
            ])
            await bot.send_message(call.message.chat.id, greeting, reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await call.answer("Iltimos, barcha majburiy kanallarga obuna bo'ling!", show_alert=True)

@router.callback_query(F.data == "back")
async def back_callback(call: types.CallbackQuery):
    await call.message.delete()
    await start_handler(call.message)
    await call.answer()

@router.callback_query(F.data == "enter_code")
async def enter_code_callback(call: types.CallbackQuery):
    await call.message.delete()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
    ])
    await call.message.answer("🔑 Anime kodini kiriting:", reply_markup=keyboard)
    await call.answer()

@router.message(Command('admin'))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!")
        return
    username = message.from_user.first_name or "Admin"
    greeting = f"👋 <b>Assalomu aleykum, {username}!</b> 🎛\n\nAdmin paneliga xush kelibsiz. Quyidagi funksiyalardan foydalaning:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Anime qoʻshish", callback_data="add_anime")],
        [InlineKeyboardButton(text="🗑 Anime oʻchirish", callback_data="delete_anime")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="👨‍💼 Admin qoʻshish", callback_data="add_admin")],
        [InlineKeyboardButton(text="❌ Admin oʻchirish", callback_data="remove_admin")],
        [InlineKeyboardButton(text="➕ Kanal qoʻshish", callback_data="add_channel_title")],
        [InlineKeyboardButton(text="🗑 Kanal oʻchirish", callback_data="remove_channel")],
        [InlineKeyboardButton(text="👥 Adminlar roʻyxati", callback_data="admins_list")],
        [InlineKeyboardButton(text="📋 Animelar roʻyxati", callback_data="anime_list")],
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
    ])
    await message.answer(greeting, reply_markup=keyboard)

@router.callback_query(F.data.in_({"add_anime", "delete_anime", "stats", "add_admin", "remove_admin", "admins_list", "anime_list", "add_channel_title", "remove_channel"}))
async def admin_callbacks(call: types.CallbackQuery):
    await call.message.delete()
    user_id = call.from_user.id
    data = call.data
    if data == "add_anime":
        user_states[user_id] = ADD_ANIME_CODE
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("➕ Yangi anime uchun noyob kod kiriting (masalan: anime001):", reply_markup=keyboard)
    elif data == "delete_anime":
        user_states[user_id] = DELETE_ANIME
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("🗑 Oʻchirish uchun anime kodini kiriting:", reply_markup=keyboard)
    elif data == "stats":
        total_users, total_anime, monthly, weekly = get_stats()
        stats_msg = f"📊 <b>Statistika:</b>\n\n👥 Jami foydalanuvchilar: {total_users}\n🎬 Jami animelar: {total_anime}\n📅 Oylik yangi: {monthly}\n📊 Haftalik yangi: {weekly}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer(stats_msg, reply_markup=keyboard)
    elif data == "add_admin":
        user_states[user_id] = ADD_ADMIN
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("👨‍💼 Yangi admin uchun user ID kiriting (raqam):", reply_markup=keyboard)
    elif data == "remove_admin":
        user_states[user_id] = REMOVE_ADMIN
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("❌ Oʻchirish uchun admin user ID kiriting (raqam):", reply_markup=keyboard)
    elif data == "add_channel_title":
        user_states[user_id] = ADD_CHANNEL_TITLE
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("➕ Kanal uchun nom kiriting (inline tugma nomi):", reply_markup=keyboard)
    elif data == "remove_channel":
        user_states[user_id] = REMOVE_CHANNEL
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer("🗑 Oʻchirish uchun kanal URL kiriting (masalan: https://t.me/channel):", reply_markup=keyboard)
    elif data == "admins_list":
        admins = get_admins_list()
        if not admins:
            msg = "👥 <b>Adminlar roʻyxati boʻsh.</b>"
        else:
            msg = "👥 <b>Adminlar roʻyxati:</b>\n\n"
            for admin_id in admins:
                try:
                    chat = await bot.get_chat(admin_id)
                    username = f"@{chat.username}" if chat.username else "Noma'lum"
                    first_name = chat.first_name or ""
                    msg += f"• ID: <code>{admin_id}</code> - {username} ({first_name})\n"
                except:
                    msg += f"• ID: <code>{admin_id}</code> - Ma'lumot topilmadi\n"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer(msg, reply_markup=keyboard)
    elif data == "anime_list":
        animes = get_anime_list()
        if not animes:
            msg = "📋 <b>Animelar roʻyxati boʻsh.</b>"
        else:
            msg = "📋 <b>Animelar roʻyxati:</b>\n\n"
            for code, name in animes:
                msg += f"• <code>{code}</code> - {name}\n"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await call.message.answer(msg, reply_markup=keyboard)
    await call.answer()

@router.message(Command('animelar'))
async def animelar_handler(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz!")
        return
    user_states[message.from_user.id] = ANIMELAR_CODE
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
    ])
    await message.answer("🔑 Anime kodini kiriting (deep link olish uchun):", reply_markup=keyboard)

@router.message(F.text, lambda message: message.from_user.id in user_states)
async def state_handler(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    text = message.text.strip()
    
    if state == ADD_ANIME_CODE:
        code = text
        cursor.execute('SELECT * FROM anime WHERE code = ?', (code,))
        if cursor.fetchone():
            await message.answer("❌ Bu kod allaqachon mavjud! Boshqa kod tanlang.")
            return
        upload_data[user_id]['code'] = code
        user_states[user_id] = ADD_ANIME_NAME
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await message.answer("📝 Anime nomini kiriting (faqat roʻyxat uchun, videolardagi matnni oʻzgartirmaydi):", reply_markup=keyboard)
    
    elif state == ADD_ANIME_NAME:
        name = text
        upload_data[user_id]['name'] = name
        user_states[user_id] = ADD_ANIME_EPISODES
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await message.answer("🔢 Nechta qism yuklaysiz? (son kiriting):", reply_markup=keyboard)
    
    elif state == ADD_ANIME_EPISODES:
        try:
            episodes = int(text)
            if episodes <= 0:
                raise ValueError
            code = upload_data[user_id]['code']
            name = upload_data[user_id]['name']
            cursor.execute('INSERT INTO anime (code, name, episodes) VALUES (?, ?, ?)', (code, name, episodes))
            conn.commit()
            upload_data[user_id]['episodes_left'] = episodes
            upload_data[user_id]['current_episode'] = 1
            user_states[user_id] = ADD_ANIME_UPLOAD
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
            ])
            await message.answer(f"✅ Ma'lumotlar saqlandi! Endi {episodes} ta video yuboring. Har biriga caption qoʻshing (matn va video bir vaqtda). Videolarni ketma-ket yuboring, xato boʻlmaydi.", reply_markup=keyboard)
        except ValueError:
            await message.answer("❌ Toʻgʻri son kiriting!")
    
    elif state == DELETE_ANIME:
        code = text
        cursor.execute('DELETE FROM anime WHERE code = ?', (code,))
        deleted_anime = cursor.rowcount
        cursor.execute('DELETE FROM episodes WHERE code = ?', (code,))
        conn.commit()
        if deleted_anime > 0:
            await message.answer(f"✅ {code} kodli anime va barcha qismlari oʻchirildi.")
        else:
            await message.answer("❌ Bunday kod topilmadi!")
        del user_states[user_id]
    
    elif state == ADD_ADMIN:
        try:
            admin_id = int(text)
            cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            await message.answer(f"✅ {admin_id} ID admin qoʻshildi (agar allaqachon boʻlmasa).")
        except ValueError:
            await message.answer("❌ Toʻgʻri raqamli ID kiriting!")
        del user_states[user_id]
    
    elif state == REMOVE_ADMIN:
        try:
            admin_id = int(text)
            if admin_id == initial_admin_id:
                await message.answer("❌ Oʻzingizni oʻchira olmaysiz!")
                del user_states[user_id]
                return
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            await message.answer(f"✅ {admin_id} ID admin oʻchirildi.")
        except ValueError:
            await message.answer("❌ Toʻgʻri raqamli ID kiriting!")
        del user_states[user_id]
    
    elif state == ADD_CHANNEL_TITLE:
        upload_data[user_id]['channel_title'] = text
        user_states[user_id] = ADD_CHANNEL_URL
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await message.answer("➕ Kanal uchun URL kiriting (masalan: https://t.me/channel):", reply_markup=keyboard)
    
    elif state == ADD_CHANNEL_URL:
        url = text.strip()
        if not url.startswith('https://t.me/'):
            await message.answer("❌ URL noto‘g‘ri! Faqat https://t.me/ bilan boshlanishi kerak.")
            del user_states[user_id]
            return
        title = upload_data[user_id]['channel_title']
        cursor.execute('INSERT OR IGNORE INTO channels (title, url) VALUES (?, ?)', (title, url))
        conn.commit()
        await message.answer(f"✅ Kanal qo‘shildi: <b>{title}</b> (<a href='{url}'>{url}</a>)")
        del user_states[user_id]
    
    elif state == REMOVE_CHANNEL:
        try:
            url = text.strip()
            if not url.startswith('https://t.me/'):
                await message.answer("❌ URL noto‘g‘ri! Faqat https://t.me/ bilan boshlanishi kerak.")
                return
            cursor.execute('DELETE FROM channels WHERE url = ?', (url,))
            if cursor.rowcount > 0:
                await message.answer(f"✅ Kanal o‘chirildi: {url}")
            else:
                await message.answer("❌ Bunday kanal topilmadi!")
        except Exception as e:
            await message.answer("❌ Xatolik yuz berdi! To‘g‘ri URL kiriting.")
        del user_states[user_id]
    
    elif state == ANIMELAR_CODE:
        code = text
        cursor.execute('SELECT * FROM anime WHERE code = ?', (code,))
        if not cursor.fetchone():
            await message.answer("❌ Bu kod mavjud emas!")
            del user_states[user_id]
            return
        me = await bot.get_me()
        deep_link = f"https://t.me/{me.username}?start={code}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await message.answer(f"🔗 Yuklash uchun deep link: <a href='{deep_link}'>{deep_link}</a>\n\nBu linkka bosilganda avto /start ishga tushadi va 1-qism chiqadi, inline tugmalar bilan.", reply_markup=keyboard, disable_web_page_preview=True)
        del user_states[user_id]

@router.message(F.video)
async def video_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id] != ADD_ANIME_UPLOAD:
        await message.answer("❌ Hozir video yuklash rejimida emassiz. /admin orqali boshlang.")
        return
    
    if 'episodes_left' not in upload_data[user_id] or upload_data[user_id]['episodes_left'] <= 0:
        await message.answer("✅ Barcha qismlar yuklandi! Anime tayyor.")
        if user_id in user_states:
            del user_states[user_id]
        return
    
    code = upload_data[user_id]['code']
    episode_num = upload_data[user_id]['current_episode']
    file_id = message.video.file_id
    caption = message.caption or f"{code} - {episode_num}-qism"
    
    cursor.execute('INSERT OR REPLACE INTO episodes (code, episode_num, file_id, caption) VALUES (?, ?, ?, ?)',
                   (code, episode_num, file_id, caption))
    conn.commit()
    
    upload_data[user_id]['episodes_left'] -= 1
    upload_data[user_id]['current_episode'] += 1
    
    status = f"✅ {episode_num}-qism yuklandi! Caption: {caption[:50]}..." if len(caption) > 50 else f"✅ {episode_num}-qism yuklandi! Caption: {caption}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
    ])
    await message.answer(status, reply_markup=keyboard)
    
    if upload_data[user_id]['episodes_left'] == 0:
        await message.answer("🎉 Barcha qismlar muvaffaqiyatli yuklandi! Anime tayyor.")
        if user_id in user_states:
            del user_states[user_id]

@router.message()
async def code_handler(message: types.Message):
    if message.from_user.id in user_states:
        return  # State handler yoki video handler tutsin
    code = message.text.strip() if message.text else ""
    if code:
        cursor.execute('SELECT * FROM anime WHERE code = ?', (code,))
        if cursor.fetchone():
            await show_anime_episode(message.chat.id, code, 1)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
            ])
            await message.answer("❌ Notoʻgʻri kod! Toʻgʻri anime kodini kiriting yoki /start dan boshlang.", reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Ortga", callback_data="back")]
        ])
        await message.answer("❌ Iltimos, anime kodini matn sifatida kiriting yoki /start dan boshlang.", reply_markup=keyboard)

async def show_anime_episode(chat_id, code, episode_num):
    cursor.execute('SELECT e.file_id, e.caption, a.episodes FROM anime a JOIN episodes e ON a.code = e.code WHERE e.code = ? AND e.episode_num = ?',
                   (code, episode_num))
    result = cursor.fetchone()
    if not result:
        await bot.send_message(chat_id, "❌ Ushbu qism topilmadi!")
        return
    
    file_id, caption, total_episodes = result
    cursor.execute('SELECT name FROM anime WHERE code = ?', (code,))
    anime_name = cursor.fetchone()[0]
    
    intro_msg = f"🎬 <b>{anime_name}</b>\n📺 {episode_num}-qism\n\nIltimos, videoni tomosha qiling."
    
    keyboard = generate_episode_keyboard(code, episode_num, total_episodes)
    
    # Eski videoni o'chirish
    try:
        async for msg in bot.get_updates(offset=-1, limit=5):  # Bu xavfli, o'rnini boshqa yechim bilan almashtirish kerak
            if msg.message and msg.message.chat.id == chat_id and msg.message.video and msg.message.caption == caption:
                try:
                    await bot.delete_message(chat_id, msg.message.message_id)
                except:
                    pass
    except:
        pass  # Xatolikni e'tiborsiz qoldiraman
    
    await bot.send_message(chat_id, intro_msg, reply_markup=keyboard)
    await bot.send_video(chat_id, file_id, caption=caption, reply_markup=keyboard)

@router.callback_query(lambda c: c.data.startswith("episode_"))
async def episode_callback(call: types.CallbackQuery):
    parts = call.data.split("_")
    if len(parts) != 3:
        await call.answer()
        return
    _, code, episode_str = parts
    try:
        episode_num = int(episode_str)
    except ValueError:
        await call.answer()
        return
    
    cursor.execute('SELECT episodes FROM anime WHERE code = ?', (code,))
    total = cursor.fetchone()
    if not total:
        await call.answer("❌ Anime topilmadi!")
        return
    total_episodes = total[0]
    
    current_keyboard = call.message.reply_markup
    if current_keyboard:
        for row in current_keyboard.inline_keyboard:
            for btn in row:
                if btn.callback_data == call.data and "✅" in btn.text:
                    await call.answer("Bu qism allaqachon tanlangan!", show_alert=True)
                    return
    
    try:
        await call.message.delete()
    except:
        pass
    
    await show_anime_episode(call.message.chat.id, code, episode_num)
    await call.answer()

async def main():
    try:
        await dp.start_polling(bot)
    finally:
        conn.close()

if __name__ == '__main__':
    print("Bot ishga tushdi! Admin ID: 5668810530")
    asyncio.run(main())
