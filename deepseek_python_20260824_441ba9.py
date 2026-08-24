#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HENSON SHOP — бот-магазин с полной автоматизацией
"""

import asyncio
import logging
import sqlite3
import json
import time
import threading
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============================================================
# НАСТРОЙКИ (ЗАМЕНИТЬ НА СВОИ)
# ============================================================
BOT_TOKEN = "8384471317:AAHXF6XqzJ2sErOKZskD1j2WONSnmmeEoOc"  # твой токен
ADMIN_ID = 8826333024                                         # твой ID
WEBAPP_URL = "https://motivationsyt077-bot.github.io/TGBOTBB/"  # ЗАМЕНИ НА СВОЙ URL после деплоя WebApp

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============================================================
# БАЗА ДАННЫХ
# ============================================================
def init_db():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        referrer_id INTEGER,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        country TEXT,
        phone TEXT,
        status TEXT DEFAULT 'available',
        price INTEGER,
        created_at TEXT,
        sold_to INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        account_id INTEGER,
        purchase_date TEXT,
        price INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS countries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        code TEXT
    )''')
    c.execute("SELECT COUNT(*) FROM countries")
    if c.fetchone()[0] == 0:
        countries = [
            ('Россия', 'RU'), ('США', 'US'), ('Германия', 'DE'),
            ('Узбекистан', 'UZ'), ('Казахстан', 'KZ'), ('Турция', 'TR'),
            ('Гренландия', 'GL'), ('Алжир', 'DZ'), ('Кюрасао', 'CW'),
            ('Мавритания', 'MR'), ('Япония', 'JP')
        ]
        c.executemany("INSERT INTO countries (name, code) VALUES (?, ?)", countries)
    conn.commit()
    conn.close()

# ============================================================
# ФУНКЦИИ БАЗЫ ДАННЫХ
# ============================================================
def get_user(user_id, username=None):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username, created_at) VALUES (?, ?, ?)",
                  (user_id, username, datetime.now().isoformat()))
        conn.commit()
        user = (user_id, username, 0, None, datetime.now().isoformat())
    conn.close()
    return user

def get_balance(user_id):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    return c.fetchone()[0]

def update_balance(user_id, amount):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
    conn.commit()
    conn.close()

def get_available_accounts(category=None, country=None):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    query = "SELECT * FROM accounts WHERE status='available'"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    if country:
        query += " AND country=?"
        params.append(country)
    c.execute(query, params)
    accounts = c.fetchall()
    conn.close()
    return accounts

def get_account_count(category=None, country=None):
    return len(get_available_accounts(category, country))

def get_category_counts():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT category, COUNT(*) FROM accounts WHERE status='available' GROUP BY category")
    result = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in result}

def buy_account(user_id, category, country):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE status='available' AND category=? AND country=? LIMIT 1",
              (category, country))
    account = c.fetchone()
    if not account:
        conn.close()
        return None
    account_id, _, _, phone, _, price, _, _ = account
    balance = get_balance(user_id)
    if balance < price:
        conn.close()
        return None
    update_balance(user_id, -price)
    c.execute("UPDATE accounts SET status='sold', sold_to=? WHERE id=?", (user_id, account_id))
    c.execute("INSERT INTO purchases (user_id, account_id, purchase_date, price) VALUES (?, ?, ?, ?)",
              (user_id, account_id, datetime.now().isoformat(), price))
    conn.commit()
    conn.close()
    return {'phone': phone, 'price': price}

def get_purchases_count(user_id):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_user_count():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_purchases(user_id, limit=10):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("""
        SELECT a.phone, p.price, p.purchase_date 
        FROM purchases p 
        JOIN accounts a ON p.account_id = a.id 
        WHERE p.user_id = ? 
        ORDER BY p.purchase_date DESC 
        LIMIT ?
    """, (user_id, limit))
    orders = c.fetchall()
    conn.close()
    return orders

def get_total_sales():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases")
    return c.fetchone()[0]

def get_total_balance_sum():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT SUM(balance) FROM users")
    return c.fetchone()[0] or 0

# ============================================================
# КЛАВИАТУРЫ
# ============================================================
def main_menu_keyboard():
    counts = get_category_counts()
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🆕 Новые аккаунты [{counts.get('new', 0)} шт.]", callback_data="category_new")
    builder.button(text=f"⏳ Аккаунты с отлетой [{counts.get('old', 0)} шт.]", callback_data="category_old")
    builder.button(text=f"⭐ Уникальные аккаунты [{counts.get('unique', 0)} шт.]", callback_data="category_unique")
    builder.button(text="👤 Профиль и баланс", callback_data="profile")
    builder.button(text="📜 Правила", callback_data="rules")
    builder.button(text="⭐ Отзывы", callback_data="reviews")
    builder.button(text="🛠 Тех. поддержка", callback_data="support")
    builder.adjust(1, 1, 1, 1, 2)
    return builder.as_markup()

def profile_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пополнить баланс", callback_data="deposit")
    builder.button(text="💸 Перевести деньги", callback_data="transfer")
    builder.button(text="📦 Мои заказы", callback_data="my_orders")
    builder.button(text="👥 Рефералка", callback_data="referral")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

def country_keyboard(category):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT country FROM accounts WHERE category=? AND status='available'", (category,))
    countries = [row[0] for row in c.fetchall()]
    conn.close()
    builder = InlineKeyboardBuilder()
    for country in countries:
        count = get_account_count(category, country)
        builder.button(text=f"{country} [{count}]", callback_data=f"buy_{category}_{country}")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back")
    return builder.as_markup()

def webapp_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Открыть магазин (цветные кнопки)", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================
@dp.message(Command("start"))
async def start(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.username)
    me = await bot.get_me()
    counts = get_category_counts()
    await message.answer(
        f"<b>🟢 HENSON SHOP</b> – купить аккаунт\n"
        f"👥 {get_user_count()} users\n\n"
        f"<b>ДОБРО ПОЖАЛОВАТЬ</b>\n"
        f"@{me.username}\n\n"
        f"<b>HENSON SHOP</b> — Сервис продажи готовых тг аккаунтов с автоматической выдачей 24/7\n\n"
        f"<b>Что у нас есть:</b>\n"
        f"• Новые, свежие аккаунты от 90₽\n"
        f"• С отлетой — проверенные временем\n"
        f"• Уникальные — под определенные цели\n\n"
        f"Обязательно ознакомьтесь с правилами и условиями!\n\n"
        f"Новые аккаунты [{counts.get('new', 0)} шт.]\n"
        f"Аккаунты с отлетой [{counts.get('old', 0)} шт.]\n"
        f"Уникальные аккаунты [{counts.get('unique', 0)} шт.]",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    await message.answer(
        "🎨 <b>Цветные кнопки доступны в приложении</b>",
        parse_mode="HTML",
        reply_markup=webapp_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("category_"))
async def show_category(callback: types.CallbackQuery):
    category = callback.data.split("_")[1]
    names = {'new': '🆕 Новые аккаунты', 'old': '⏳ Аккаунты с отлетой', 'unique': '⭐ Уникальные аккаунты'}
    await callback.message.edit_text(
        f"<b>{names[category]}</b>\n\n"
        "Для безопасности входа используйте прокси по региону.\n\n"
        "<b>Выберите страну:</b>",
        parse_mode="HTML",
        reply_markup=country_keyboard(category)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_account_handler(callback: types.CallbackQuery):
    _, category, country = callback.data.split("_", 2)
    result = buy_account(callback.from_user.id, category, country)
    if not result:
        await callback.answer("❌ Недостаточно средств или нет аккаунтов", show_alert=True)
        return
    await callback.message.edit_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"📱 <b>Номер:</b> <code>{result['phone']}</code>\n"
        f"💰 <b>Стоимость:</b> {result['price']}₽",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    balance = get_balance(callback.from_user.id)
    purchases = get_purchases_count(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>👤 ПРОФИЛЬ</b>\n\n"
        f"Имя: @{user[1] or 'Не указано'}\n"
        f"ID: {user[0]}\n\n"
        f"Покупок: {purchases}\n"
        f"Баланс: <b>{balance} ₽</b>",
        parse_mode="HTML",
        reply_markup=profile_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_to_menu(callback: types.CallbackQuery):
    await start(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "deposit")
async def deposit(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>💰 ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
        "Оплатите через Crypto Bot по ссылке:\n"
        "<a href='https://t.me/send?start=IVAQtUoLIFnJ'>Оплатить сейчас</a>\n\n"
        "После оплаты напишите в техподдержку с указанием суммы и ID.\n"
        "Баланс пополнится вручную в течение 5 минут.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "my_orders")
async def my_orders(callback: types.CallbackQuery):
    orders = get_purchases(callback.from_user.id)
    if not orders:
        await callback.message.edit_text("📦 <b>Заказов нет</b>", parse_mode="HTML", reply_markup=back_keyboard())
        await callback.answer()
        return
    text = "📦 <b>Мои заказы</b>\n\n"
    for i, (phone, price, date) in enumerate(orders, 1):
        text += f"{i}. 📱 <code>{phone}</code> — {price}₽ ({date[:10]})\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "referral")
async def referral(callback: types.CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={callback.from_user.id}"
    await callback.message.edit_text(
        f"<b>👥 РЕФЕРАЛКА</b>\n\n"
        f"Приглашай друзей и получай 10₽ за каждого!\n"
        f"Твоя ссылка:\n<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "rules")
async def rules(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>📜 ПРАВИЛА</b>\n\n"
        "1. Аккаунты выдаются автоматически после оплаты.\n"
        "2. Возврат только при технической проблеме.\n"
        "3. Запрещён спам — блокировка.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "reviews")
async def reviews(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>⭐ ОТЗЫВЫ</b>\n\n"
        "🌟 «Отличный сервис!» — @user1\n"
        "🌟 «Всё быстро, рекомендую» — @user2",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "support")
async def support(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "<b>🛠 ПОДДЕРЖКА</b>\n\n"
        "По вопросам пишите в Telegram: @support_username",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return
    await message.answer("<b>👑 АДМИН-ПАНЕЛЬ</b>\n\n/add_balance <user_id> <сумма> — пополнить\n/stats — статистика", parse_mode="HTML")

@dp.message(Command("add_balance"))
async def add_balance(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /add_balance <user_id> <сумма>")
        return
    try:
        user_id = int(parts[1])
        amount = int(parts[2])
        update_balance(user_id, amount)
        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount} ₽")
    except:
        await message.answer("❌ Ошибка. Проверь формат.")

@dp.message(Command("stats"))
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = get_user_count()
    available = sum(get_category_counts().values())
    sales = get_total_sales()
    total_balance = get_total_balance_sum()
    await message.answer(
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Доступно: {available}\n"
        f"💰 Продаж: {sales}\n"
        f"💵 Общий баланс: {total_balance} ₽",
        parse_mode="HTML"
    )

# ============================================================
# ПИНГ-ФУНКЦИЯ ДЛЯ БЕСПЛАТНОГО ХОСТИНГА (чтобы не засыпал)
# ============================================================
def keep_alive():
    url = "https://henson-shop-bot.onrender.com"  # ЗАМЕНИТЬ НА РЕАЛЬНЫЙ URL ПОСЛЕ ДЕПЛОЯ
    while True:
        try:
            requests.get(url, timeout=5)
        except:
            pass
        time.sleep(300)

# ============================================================
# ЗАПУСК
# ============================================================
async def main():
    init_db()
    print("✅ HENSON SHOP запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем пинг в фоновом потоке (если бот на Render)
    threading.Thread(target=keep_alive, daemon=True).start()
    asyncio.run(main())