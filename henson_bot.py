#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HENSON SHOP — полностью автоматизированный бот-магазин
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
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ============================================================
# НАСТРОЙКИ
# ============================================================
BOT_TOKEN = "8384471317:AAHXF6XqzJ2sErOKZskD1j2WONSnmmeEoOc"
ADMIN_ID = 8826333024

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
    c.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        approved INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        timestamp TEXT
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
# ФУНКЦИИ БД
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
    return c.fetchone()[0]

def get_user_count():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]

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

def add_review(user_id, text):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("INSERT INTO reviews (user_id, text, created_at) VALUES (?, ?, ?)",
              (user_id, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_approved_reviews():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT user_id, text, created_at FROM reviews WHERE approved=1 ORDER BY created_at DESC LIMIT 20")
    reviews = c.fetchall()
    conn.close()
    return reviews

def get_pending_reviews():
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT id, user_id, text, created_at FROM reviews WHERE approved=0 ORDER BY created_at ASC")
    reviews = c.fetchall()
    conn.close()
    return reviews

def approve_review(review_id):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("UPDATE reviews SET approved=1 WHERE id=?", (review_id,))
    conn.commit()
    conn.close()

def delete_review(review_id):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("DELETE FROM reviews WHERE id=?", (review_id,))
    conn.commit()
    conn.close()

def log_admin_action(admin_id, action):
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (admin_id, action, timestamp) VALUES (?, ?, ?)",
              (admin_id, action, datetime.now().isoformat()))
    conn.commit()
    conn.close()

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
        builder.button(text=f"🌍 {country} [{count}]", callback_data=f"buy_{category}_{country}")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back")
    return builder.as_markup()

def admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить аккаунт", callback_data="admin_add_account")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="💰 Топ пользователей", callback_data="admin_top")
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.button(text="⭐ Отзывы (модерация)", callback_data="admin_reviews")
    builder.button(text="⚙️ Управление аккаунтами", callback_data="admin_manage")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# ============================================================
# FSM ДЛЯ ДОБАВЛЕНИЯ АККАУНТА
# ============================================================
class AddAccountStates(StatesGroup):
    category = State()
    country = State()
    phone = State()
    price = State()

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================
@dp.message(Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    me = await bot.get_me()
    counts = get_category_counts()
    text = (
        f"<b>🟢 HENSON SHOP</b> – купить аккаунт\n"
        f"👥 {get_user_count()} users\n\n"
        f"<b>ДОБРО ПОЖАЛОВАТЬ</b>\n"
        f"@{me.username}\n\n"
        f"<b>HENSON SHOP</b> — Сервис продажи готовых тг аккаунтов с автоматической выдачей 24/7\n\n"
        f"<b>Что у нас есть:</b>\n"
        f"• 🆕 Новые, свежие аккаунты от 90₽\n"
        f"• ⏳ С отлетой — проверенные временем\n"
        f"• ⭐ Уникальные — под определенные цели\n\n"
        f"Обязательно ознакомьтесь с правилами и условиями!\n\n"
        f"🆕 Новые аккаунты [{counts.get('new', 0)} шт.]\n"
        f"⏳ Аккаунты с отлетой [{counts.get('old', 0)} шт.]\n"
        f"⭐ Уникальные аккаунты [{counts.get('unique', 0)} шт.]"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())
    
    # Реферальная ссылка
    if message.text and len(message.text.split()) > 1:
        try:
            ref_id = int(message.text.split()[1])
            if ref_id != message.from_user.id:
                update_balance(ref_id, 10)
                await bot.send_message(ref_id, f"👥 Реферальный бонус! +10₽ за приглашённого @{message.from_user.username or message.from_user.id}")
        except:
            pass

@dp.callback_query(lambda c: c.data.startswith("category_"))
async def show_category(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    names = {'new': '🆕 Новые аккаунты', 'old': '⏳ Аккаунты с отлетой', 'unique': '⭐ Уникальные аккаунты'}
    await callback.message.edit_text(
        f"<b>{names[category]}</b>\n\n"
        "🌍 <b>Выберите страну:</b>",
        parse_mode="HTML",
        reply_markup=country_keyboard(category)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_account_handler(callback: CallbackQuery):
    _, category, country = callback.data.split("_", 2)
    result = buy_account(callback.from_user.id, category, country)
    if not result:
        await callback.answer("❌ Недостаточно средств или нет аккаунтов", show_alert=True)
        return
    await callback.message.edit_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"📱 <b>Номер:</b> <code>{result['phone']}</code>\n"
        f"💰 <b>Стоимость:</b> {result['price']}₽\n\n"
        f"<i>Инструкция по входу в аккаунт: ...</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    balance = get_balance(callback.from_user.id)
    purchases = get_purchases_count(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>👤 ПРОФИЛЬ</b>\n\n"
        f"Имя: @{user[1] or 'Не указано'}\n"
        f"ID: {user[0]}\n\n"
        f"🛒 Покупок: {purchases}\n"
        f"💰 Баланс: <b>{balance} ₽</b>",
        parse_mode="HTML",
        reply_markup=profile_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_to_menu(callback: CallbackQuery):
    await start(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "deposit")
async def deposit(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>💰 ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
        "🔹 <b>Способ 1: Crypto Bot</b>\n"
        "Перейдите по ссылке и оплатите:\n"
        "<a href='https://t.me/send?start=IVAQtUoLIFnJ'>Оплатить сейчас</a>\n\n"
        "🔹 <b>Способ 2: Ручной перевод</b>\n"
        "Реквизиты: ...\n\n"
        "После оплаты напишите в техподдержку с указанием суммы и ID.\n"
        "Баланс пополнится вручную в течение 5 минут.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "my_orders")
async def my_orders(callback: CallbackQuery):
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
async def referral(callback: CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={callback.from_user.id}"
    await callback.message.edit_text(
        f"<b>👥 РЕФЕРАЛКА</b>\n\n"
        f"Приглашай друзей и получай +10₽ за каждого!\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"Друзья получают скидку 5% на первую покупку.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "rules")
async def rules(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>📜 ПРАВИЛА И УСЛОВИЯ</b>\n\n"
        "1. Аккаунты выдаются автоматически после оплаты.\n"
        "2. Возврат средств только при технической проблеме.\n"
        "3. Запрещён спам с аккаунтов — блокировка без возврата.\n"
        "4. За нарушение правил — бан в сервисе.\n\n"
        "По всем вопросам — техподдержка.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "reviews")
async def show_reviews(callback: CallbackQuery):
    reviews = get_approved_reviews()
    if not reviews:
        await callback.message.edit_text(
            "⭐ <b>ОТЗЫВЫ</b>\n\nПока нет отзывов. Будьте первым!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="write_review")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
            ])
        )
        await callback.answer()
        return
    text = "⭐ <b>ОТЗЫВЫ</b>\n\n"
    for user_id, review_text, created_at in reviews:
        user = await bot.get_chat(user_id)
        username = user.username or str(user_id)
        text += f"<b>@{username}</b>\n{review_text}\n— {created_at[:10]}\n\n"
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="write_review")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "write_review")
async def write_review(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Напишите ваш отзыв (не более 500 символов):")
    await state.set_state("waiting_review")
    await callback.answer()

@dp.message(StateFilter("waiting_review"), F.text)
async def save_review(message: Message, state: FSMContext):
    add_review(message.from_user.id, message.text[:500])
    await message.answer("✅ Отзыв отправлен на модерацию. После проверки он будет опубликован.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "support")
async def support(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>🛠 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА</b>\n\n"
        "По всем вопросам пишите:\n"
        "📩 Telegram: @support_username\n"
        "📧 Email: support@henson.shop\n\n"
        "Отвечаем в течение 15 минут.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return
    await message.answer(
        "<b>👑 АДМИН-ПАНЕЛЬ</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )

@dp.callback_query(lambda c: c.data == "admin_add_account")
async def admin_add_account_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.answer("➕ <b>Добавление аккаунта</b>\n\nВведите категорию (new/old/unique):")
    await state.set_state(AddAccountStates.category)
    await callback.answer()

@dp.message(AddAccountStates.category, F.text)
async def add_account_category(message: Message, state: FSMContext):
    if message.text not in ('new', 'old', 'unique'):
        await message.answer("❌ Категория должна быть new, old или unique")
        return
    await state.update_data(category=message.text)
    await message.answer("Введите страну (например: Россия):")
    await state.set_state(AddAccountStates.country)

@dp.message(AddAccountStates.country, F.text)
async def add_account_country(message: Message, state: FSMContext):
    await state.update_data(country=message.text)
    await message.answer("Введите номер телефона (в формате +79001234567):")
    await state.set_state(AddAccountStates.phone)

@dp.message(AddAccountStates.phone, F.text)
async def add_account_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите цену в рублях (только число):")
    await state.set_state(AddAccountStates.price)

@dp.message(AddAccountStates.price, F.text)
async def add_account_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        data = await state.get_data()
        conn = sqlite3.connect('henson.db')
        c = conn.cursor()
        c.execute("INSERT INTO accounts (category, country, phone, price, created_at) VALUES (?, ?, ?, ?, ?)",
                  (data['category'], data['country'], data['phone'], price, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        log_admin_action(ADMIN_ID, f"Добавлен аккаунт: {data['category']}, {data['country']}, {data['phone']}, {price}₽")
        await message.answer("✅ Аккаунт добавлен!")
        await state.clear()
    except:
        await message.answer("❌ Ошибка. Введите число.")

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    users = get_user_count()
    available = sum(get_category_counts().values())
    sales = get_total_sales()
    total_balance = get_total_balance_sum()
    await callback.message.edit_text(
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Доступно аккаунтов: {available}\n"
        f"💰 Продаж: {sales}\n"
        f"💵 Общий баланс: {total_balance} ₽",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_top")
async def admin_top(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT id, username, balance FROM users ORDER BY balance DESC LIMIT 20")
    top = c.fetchall()
    conn.close()
    text = "💰 <b>ТОП ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    for i, (uid, username, balance) in enumerate(top, 1):
        text += f"{i}. @{username or str(uid)} — {balance} ₽\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.answer("📢 Введите текст сообщения для рассылки:")
    await state.set_state("broadcast_text")
    await callback.answer()

@dp.message(StateFilter("broadcast_text"), F.text)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users")
    users = c.fetchall()
    conn.close()
    sent = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{message.text}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка отправлена {sent} пользователям.")
    log_admin_action(ADMIN_ID, f"Рассылка: {message.text[:50]}...")
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_reviews")
async def admin_reviews(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    pending = get_pending_reviews()
    if not pending:
        await callback.message.edit_text("⭐ Нет отзывов на модерации.", reply_markup=back_keyboard())
        await callback.answer()
        return
    text = "⭐ <b>ОТЗЫВЫ НА МОДЕРАЦИИ</b>\n\n"
    for review_id, user_id, rev_text, created_at in pending:
        user = await bot.get_chat(user_id)
        username = user.username or str(user_id)
        text += f"ID: {review_id}\n@{username}\n{rev_text}\n{created_at[:10]}\n\n"
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_review_{review_id}"),
             InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_review_{review_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("approve_review_"))
async def approve_review_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    review_id = int(callback.data.split("_")[2])
    approve_review(review_id)
    log_admin_action(ADMIN_ID, f"Одобрен отзыв ID {review_id}")
    await callback.answer("✅ Отзыв одобрен")
    await admin_reviews(callback)

@dp.callback_query(lambda c: c.data.startswith("delete_review_"))
async def delete_review_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    review_id = int(callback.data.split("_")[2])
    delete_review(review_id)
    log_admin_action(ADMIN_ID, f"Удалён отзыв ID {review_id}")
    await callback.answer("❌ Отзыв удалён")
    await admin_reviews(callback)

@dp.callback_query(lambda c: c.data == "admin_manage")
async def admin_manage_accounts(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет прав")
        return
    await callback.message.edit_text(
        "⚙️ <b>Управление аккаунтами</b>\n\n"
        "Команды для админа:\n"
        "/list_accounts — список всех аккаунтов\n"
        "/delete_account <id> — удалить аккаунт\n"
        "/edit_price <id> <новая_цена> — изменить цену",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )
    await callback.answer()

@dp.message(Command("list_accounts"))
async def list_accounts(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('henson.db')
    c = conn.cursor()
    c.execute("SELECT id, category, country, phone, price, status FROM accounts LIMIT 50")
    accounts = c.fetchall()
    conn.close()
    if not accounts:
        await message.answer("📭 Аккаунтов нет")
        return
    text = "📋 <b>Аккаунты (последние 50)</b>\n\n"
    for acc in accounts:
        text += f"ID:{acc[0]} | {acc[1]} | {acc[2]} | {acc[3]} | {acc[4]}₽ | {acc[5]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("delete_account"))
async def delete_account(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /delete_account <id>")
        return
    try:
        acc_id = int(parts[1])
        conn = sqlite3.connect('henson.db')
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        conn.commit()
        conn.close()
        log_admin_action(ADMIN_ID, f"Удалён аккаунт ID {acc_id}")
        await message.answer(f"✅ Аккаунт {acc_id} удалён")
    except:
        await message.answer("❌ Ошибка")

@dp.message(Command("edit_price"))
async def edit_price(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /edit_price <id> <новая_цена>")
        return
    try:
        acc_id = int(parts[1])
        new_price = int(parts[2])
        conn = sqlite3.connect('henson.db')
        c = conn.cursor()
        c.execute("UPDATE accounts SET price=? WHERE id=?", (new_price, acc_id))
        conn.commit()
        conn.close()
        log_admin_action(ADMIN_ID, f"Изменена цена аккаунта {acc_id} на {new_price}")
        await message.answer(f"✅ Цена аккаунта {acc_id} изменена на {new_price}₽")
    except:
        await message.answer("❌ Ошибка")

@dp.message(Command("add_balance"))
async def add_balance(message: Message):
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
        log_admin_action(ADMIN_ID, f"Пополнен баланс пользователя {user_id} на {amount}₽")
        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount} ₽")
        await bot.send_message(user_id, f"💰 Ваш баланс пополнен на {amount} ₽!")
    except:
        await message.answer("❌ Ошибка. Проверь формат.")

# ============================================================
# ПИНГ ДЛЯ RENDER
# ============================================================
def keep_alive():
    url = "https://tgkbot.onrender.com"  # замени на свой URL
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
    threading.Thread(target=keep_alive, daemon=True).start()
    asyncio.run(main())
