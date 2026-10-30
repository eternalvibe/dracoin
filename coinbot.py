import asyncio
import logging
import random
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


load_dotenv()

# ==================== НАСТРОЙКИ ====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Токен BOT_TOKEN не найден в .env файле!")

# BOT_TOKEN = "8802517848:AAHosYet7Yf1llgmzFb4kyqqfeHBUVmuce4"
TARGET_CHAT_ID = -1002614929006
ADMIN_IDS = {1955476231, 8025502507, 8595107331}

DELETE_COMMAND_MESSAGES = True

# Дроп посылок
REWARD_AMOUNT = 1
PACKAGES_PER_DAY = 2
MIN_INTERVAL_HOURS = 3

# ID кастомного эмодзи (Дракоин)
COIN_EMOJI_ID = "5411613201882200030"
COIN_EMOJI_FALLBACK = "🪙"

def coin_emoji() -> str:
    return f'<tg-emoji emoji-id="{COIN_EMOJI_ID}">{COIN_EMOJI_FALLBACK}</tg-emoji>'

# О монете
COIN_NAME = f"{coin_emoji()} Дракоин"
PACKAGE_TEXT = "Вам посылка!"
BUTTON_TEXT = "Забрать Дракоин"
BALANCE_TEXT = "Ваш баланс: {balance} {coin}"

CLAIMED_TEXT = "{user} получил {reward} {coin}"

NO_RIGHTS_TEXT = "У вас нет прав для использования этой команды."

REGISTER_SUCCESS_TEXT = "Вы зарегистрированы! Ваш стартовый баланс: {balance} {coin}."
REGISTER_ALREADY_TEXT = "Вы уже зарегистрированы. Ваш баланс: {balance} {coin}."

GIFT_USAGE_TEXT = "Использование: /dracoin @username {amount} или /dracoin user_id {amount}"
GIFT_USER_NOT_FOUND_TEXT = "Пользователь @{username} ещё не получал монеты, поэтому неизвестен боту."
GIFT_BAD_AMOUNT_TEXT = "Неверное количество: нужно целое число."
GIFT_SUCCESS_TEXT = "Пользователю {target} начислено {amount} {coin}. Новый баланс: {balance}."
GIFT_SUCCESS_BY_ID_TEXT = "Пользователю с ID {user_id} начислено {amount} {coin}. Новый баланс: {balance}."
GIFT_NO_TARGET_TEXT = "Не указан получатель. " + GIFT_USAGE_TEXT
GIFT_SUCCESS_BY_REPLY_TEXT = "Пользователю {target} начислено {amount} {coin}. Новый баланс: {balance}."
GIFT_REPLY_NO_AMOUNT_TEXT = "Укажите количество: /dracoin {amount} (ответом на сообщение)."

# Сброс балансов
RESET_CONFIRM_TEXT = (
    "⚠️ Вы уверены, что хотите обнулить балансы ВСЕХ пользователей?\n"
    "Это действие необратимо."
)
RESET_CONFIRM_BUTTON = "✅ Да, обнулить"
RESET_CANCEL_BUTTON = "❌ Отмена"
RESET_DONE_TEXT = "Балансы всех пользователей обнулены. Дата обнуления: {date}"
RESET_CANCELLED_TEXT = "Сброс отменён."
RESET_WRONG_USER_TEXT = "Эта кнопка не для вас."

# Топ богачей
TOP_HEADER = "🏆 Лидерборд Дракоинов:"
TOP_LINE = "{i}. {user} - {amount} " + coin_emoji()
TOP_EMPTY_TEXT = "Пока никто не накопил ни одного {coin}а."
TOP_LIMIT = 20
TOP_STATS_LINE = "Статистика с {date}"
TOP_NO_RESET_DATE = "—"

# По /start в ЛС
WELCOME_TEXT = (
    "Привет! Я бот с собственной валютой чата La eMe Mafia — {coin}.\n\n"
    "Время от времени я присылаю в чат сообщение «Вам посылка!» "
    "с кнопкой. Первый, кто нажмёт, получает {reward} {coin}.\n\n"
    "📊 Узнать свой баланс: /balance (в личных сообщениях).\n"
    "🏆 Рейтинг богачей: /top (в чате).\n\n"
    "Удачи в охоте за монетами!"
).format(coin=COIN_NAME, reward=REWARD_AMOUNT)

WELCOME_ADMIN_TEXT = (
    "Команды для администраторов"
    "/drop: Выдать посылку в чат"
    "/dracoin: Начислить монеты в формате /dracoin <@username или user_id> N, либо ответом на сообщение в формате /dracoin N"
    "/reset: Сбросить ВСЕ монеты у ВСЕХ участников чата (использовать с осторожностью)"
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcoins.db")
# ===================================================

logging.basicConfig(level=logging.INFO)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)


# ==================== ФИЛЬТРЫ ====================
class IsAddressedToBot(BaseFilter):
    def __init__(self, private_ok: bool = True):
        self.private_ok = private_ok

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if message.chat.type == "private":
            return self.private_ok

        text = message.text or ""
        if not text.startswith("/"):
            return False

        first_token = text.split(maxsplit=1)[0]
        if "@" not in first_token:
            return False

        mentioned = first_token.split("@", 1)[1].lower()
        expected = (BOT_USERNAME or "").lstrip("@").lower()
        return mentioned == expected
# ===================================================


# ---------- Работа с БД ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            balance INTEGER DEFAULT 0
        )
    """)
    cursor.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cursor.fetchall()}
    if "username" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "display_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def add_balance(user_id: int, amount: int, username: str | None = None,
                display_name: str | None = None):
    """Меняет баланс. username/display_name обновляются, если переданы (не None)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, display_name, balance) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            balance = balance + ?,
            username = COALESCE(?, username),
            display_name = COALESCE(?, display_name)
    """, (user_id, username, display_name, amount, amount, username, display_name))
    conn.commit()
    conn.close()

def find_user_by_username(username: str) -> int | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM users WHERE LOWER(username) = ?",
        (username.lower().lstrip("@"),)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_top_users(limit: int = 20) -> list[tuple[int, str | None, str | None, int]]:
    """Возвращает список (user_id, username, display_name, balance) по убыванию баланса, только balance > 0."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, display_name, balance FROM users "
        "WHERE balance > 0 ORDER BY balance DESC, user_id ASC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_last_package_time() -> datetime | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM state WHERE key = 'last_package_time'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0])
    return None

def set_last_package_time(dt: datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO state (key, value) VALUES ('last_package_time', ?)",
        (dt.isoformat(),)
    )
    conn.commit()
    conn.close()

# Обновление статистики
def get_last_reset_date() -> datetime | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM state WHERE key = 'last_reset_date'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return datetime.fromisoformat(row[0])
    return None

def set_last_reset_date(dt: datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO state (key, value) VALUES ('last_reset_date', ?)",
        (dt.isoformat(),)
    )
    conn.commit()
    conn.close()

def reset_all_balances():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = 0")
    conn.commit()
    conn.close()    
# --------------------------------

# ---------- ЗАПУСК БОТА ----------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

package_lock = asyncio.Lock()

BOT_USERNAME = ""


# Удаление вызовов команд
async def try_delete_command_message(message: Message):
    if not DELETE_COMMAND_MESSAGES:
        return
    try:
        await message.delete()
    except Exception:
        logging.exception("Не удалось удалить сообщение с командой")


# Отправка рандомной посылки в чат
async def send_package(chat_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=BUTTON_TEXT,
            callback_data="claim_coin",
            icon_custom_emoji_id=COIN_EMOJI_ID,
        )]
    ])
    await bot.send_message(chat_id=chat_id, text=PACKAGE_TEXT, reply_markup=keyboard)


# Алгоритм отправки
async def package_scheduler():
    await asyncio.sleep(5)
    while True:
        now = datetime.now()
        last_time = get_last_package_time()
        if last_time and (now - last_time) < timedelta(hours=MIN_INTERVAL_HOURS):
            wait_seconds = (timedelta(hours=MIN_INTERVAL_HOURS) - (now - last_time)).total_seconds()
            await asyncio.sleep(wait_seconds + random.randint(60, 600))
            continue

        base_interval_seconds = (24 * 3600) / PACKAGES_PER_DAY
        jitter_seconds = random.randint(-7200, 7200)
        wait_seconds = max(base_interval_seconds + jitter_seconds, MIN_INTERVAL_HOURS * 3600)
        await asyncio.sleep(wait_seconds)

        now = datetime.now()
        last_time = get_last_package_time()
        if last_time and (now - last_time) < timedelta(hours=MIN_INTERVAL_HOURS):
            continue

        await send_package(TARGET_CHAT_ID)
        set_last_package_time(datetime.now())


# ---------- Обработчики ----------
# Команда /start (только в ЛС)
@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type != "private":
        return
    await message.answer(WELCOME_TEXT)

# Команда /balance (только в ЛС)
@router.message(Command("balance"))
async def cmd_balance(message: Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(BALANCE_TEXT.format(balance=balance, coin=COIN_NAME))

# Команда /register - занесение в базу данных
@router.message(Command("register"), IsAddressedToBot())
async def cmd_register(message: Message):
    await try_delete_command_message(message)
    user = message.from_user
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    
    if row is not None:
        balance = row[0]
        conn.close()
        await message.answer(REGISTER_ALREADY_TEXT.format(balance=balance, coin=COIN_NAME))
        return
    
    cursor.execute("""
        INSERT INTO users (user_id, username, display_name, balance)
        VALUES (?, ?, ?, 0)
    """, (user.id, user.username, user.full_name))
    conn.commit()
    conn.close()
    
    await message.answer(REGISTER_SUCCESS_TEXT.format(balance=0, coin=COIN_NAME))

# Команда /top - рейтинг
@router.message(Command("top"), IsAddressedToBot())
async def cmd_top(message: Message):
    await try_delete_command_message(message)
    users = get_top_users(TOP_LIMIT)
    if not users:
        await message.answer(TOP_EMPTY_TEXT.format(coin=COIN_NAME))
        return

    lines = [TOP_HEADER]
    for i, (user_id, username, display_name, balance) in enumerate(users, start=1):
        if display_name and display_name.strip():
            display = display_name.strip()
        elif username:
            display = username
        else:
            display = f"ID {user_id}"
        display = display.lstrip("@").strip()
        if not display:
            display = f"ID {user_id}"
        lines.append(TOP_LINE.format(i=i, user=display, amount=balance))

    last_reset = get_last_reset_date()
    date_str = last_reset.strftime("%d.%m.%Y") if last_reset else TOP_NO_RESET_DATE
    lines.append("")
    lines.append(TOP_STATS_LINE.format(date=date_str))

    await message.answer("\n".join(lines))    

# Команда /drop - ручная отправка посылки в чат
@router.message(Command("drop"))
async def cmd_drop(message: Message):
    await try_delete_command_message(message)
    if message.from_user.id not in ADMIN_IDS:
        await message.answer(NO_RIGHTS_TEXT)
        return
    await send_package(message.chat.id)
    set_last_package_time(datetime.now())

# Команда /dracoin - ручной перевод дракоинов
@router.message(Command("dracoin"))
async def cmd_dracoin(message: Message):
    await try_delete_command_message(message)

    if message.from_user.id not in ADMIN_IDS:
        await message.answer(NO_RIGHTS_TEXT)
        return

    parts = (message.text or "").split()
    args = parts[1:]

    # Вариант 1: ответ на сообщение
    if message.reply_to_message is not None:
        if len(args) < 1:
            await message.answer(GIFT_REPLY_NO_AMOUNT_TEXT)
            return
        try:
            amount = int(args[0])
        except ValueError:
            await message.answer(GIFT_BAD_AMOUNT_TEXT)
            return

        target_user = message.reply_to_message.from_user
        if target_user is None:
            await message.answer(GIFT_USAGE_TEXT)
            return

        add_balance(
            target_user.id, amount,
            username=target_user.username,
            display_name=target_user.full_name,
        )
        new_balance = get_balance(target_user.id)
        display = target_user.full_name or f"ID {target_user.id}"
        await message.answer(GIFT_SUCCESS_BY_REPLY_TEXT.format(
            target=display, amount=amount, coin=COIN_NAME, balance=new_balance
        ))
        return

    # Вариант 2: явный тег /dracoin @username N или /dracoin user_id N
    if len(args) < 2:
        await message.answer(GIFT_USAGE_TEXT)
        return

    target_raw, amount_raw = args[0], args[1]

    try:
        amount = int(amount_raw)
    except ValueError:
        await message.answer(GIFT_BAD_AMOUNT_TEXT)
        return

    if target_raw.startswith("@"):
        username = target_raw.lstrip("@")
        user_id = find_user_by_username(username)
        if user_id is None:
            await message.answer(GIFT_USER_NOT_FOUND_TEXT.format(username=username))
            return
        add_balance(user_id, amount)
        new_balance = get_balance(user_id)
        await message.answer(GIFT_SUCCESS_TEXT.format(
            target=f"@{username}", amount=amount, coin=COIN_NAME, balance=new_balance
        ))
        return

    if target_raw.isdigit():
        user_id = int(target_raw)
        add_balance(user_id, amount)
        new_balance = get_balance(user_id)
        await message.answer(GIFT_SUCCESS_BY_ID_TEXT.format(
            user_id=user_id, amount=amount, coin=COIN_NAME, balance=new_balance
        ))
        return

    await message.answer(GIFT_USAGE_TEXT)

# Команда /reset - сброс всех монет
@router.message(Command("reset"), IsAddressedToBot())
async def cmd_reset(message: Message):
    await try_delete_command_message(message)

    if message.from_user.id not in ADMIN_IDS:
        await message.answer(NO_RIGHTS_TEXT)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=RESET_CONFIRM_BUTTON, callback_data="reset_confirm"),
            InlineKeyboardButton(text=RESET_CANCEL_BUTTON, callback_data="reset_cancel"),
        ]
    ])
    await message.answer(RESET_CONFIRM_TEXT, reply_markup=keyboard)

@router.callback_query(F.data == "reset_confirm")
async def reset_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(RESET_WRONG_USER_TEXT, show_alert=True)
        return

    reset_all_balances()
    now = datetime.now()
    set_last_reset_date(now)
    date_str = now.strftime("%d.%m.%Y")

    try:
        await callback.message.edit_text(RESET_DONE_TEXT.format(date=date_str))
    except Exception:
        logging.exception("Не удалось отредактировать сообщение после сброса")

    await callback.answer()

@router.callback_query(F.data == "reset_cancel")
async def reset_cancel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(RESET_WRONG_USER_TEXT, show_alert=True)
        return

    try:
        await callback.message.edit_text(RESET_CANCELLED_TEXT)
    except Exception:
        logging.exception("Не удалось отредактировать сообщение после отмены")

    await callback.answer()

# Взятие монеты
@router.callback_query(F.data == "claim_coin")
async def claim_coin(callback: CallbackQuery):
    async with package_lock:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            await callback.answer("Монета уже забрана!", show_alert=True)
            return

        user = callback.from_user
        add_balance(
            user.id, REWARD_AMOUNT,
            username=user.username,
            display_name=user.full_name,
        )

        display = user.full_name or f"ID {user.id}"
        try:
            await callback.message.edit_text(
                CLAIMED_TEXT.format(user=display, reward=REWARD_AMOUNT, coin=COIN_NAME)
            )
        except Exception:
            logging.exception("Не удалось отредактировать сообщение после получения монеты")

        await callback.answer(f"Вы получили {REWARD_AMOUNT} 🪙Дракоин!", show_alert=True)


# ---------- Регистрация меню команд ----------
async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="top", description="Лидерборд чата по дракоинам"),
        BotCommand(command="register", description="Регистрация в базе"),
    ])


async def main():
    global BOT_USERNAME
    init_db()
    me = await bot.get_me()
    BOT_USERNAME = (me.username or "").lower()
    await set_bot_commands()
    dp.include_router(router)
    asyncio.create_task(package_scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())