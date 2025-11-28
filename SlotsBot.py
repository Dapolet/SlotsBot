import asyncio
from asyncio import Lock
import random
import logging
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


class SlotMachine:
    def __init__(self):
        self.symbols = ['🍒', '🍋', '🍊', '🍇', '🍌', '⭐', '💎', '7️⃣', '💰']
        self.probabilities = [0.18, 0.16, 0.14, 0.12, 0.10, 0.08, 0.07, 0.06, 0.03]
        self.payouts = {
            '🍒': {3: 2, 4: 5, 5: 10},
            '🍋': {3: 3, 4: 8, 5: 15},
            '🍊': {3: 4, 4: 10, 5: 20},
            '🍇': {3: 5, 4: 15, 5: 30},
            '🍌': {3: 8, 4: 20, 5: 50},
            '⭐': {3: 10, 4: 25, 5: 75},
            '💎': {3: 15, 4: 40, 5: 100},
            '7️⃣': {3: 20, 4: 50, 5: 150},
            '💰': {3: 50, 4: 200, 5: 1000}
        }
        self.jackpot = 10000
        self.jackpot_increment = 0.1

    def spin(self, bet: int) -> Tuple[List[List[str]], int, bool]:
        """Генерация результата вращения с учетом вероятностей"""
        reels = []
        for _ in range(5):
            reel = random.choices(self.symbols, weights=self.probabilities, k=3)
            reels.append(reel)

        win_amount, is_jackpot = self.calculate_win(reels, bet)
        self.jackpot += round(bet * self.jackpot_increment)

        return reels, win_amount, is_jackpot

    def calculate_win(self, reels: List[List[str]], bet: int) -> Tuple[int, bool]:
        """Расчет выигрыша по линиям"""
        total_win = 0
        is_jackpot = False

        # Проверка линий выплат
        lines = [
            [reels[0][0], reels[1][0], reels[2][0], reels[3][0], reels[4][0]],  # Верхняя линия
            [reels[0][1], reels[1][1], reels[2][1], reels[3][1], reels[4][1]],  # Средняя линия
            [reels[0][2], reels[1][2], reels[2][2], reels[3][2], reels[4][2]],  # Нижняя линия
            [reels[0][0], reels[1][1], reels[2][2], reels[3][1], reels[4][0]],  # Диагональ 1
            [reels[0][2], reels[1][1], reels[2][0], reels[3][1], reels[4][2]],  # Диагональ 2
        ]

        for line in lines:
            count = 1
            current_sequence = 1
            symbol = ''

            for i in range(1, len(line)):
                if line[i] == line[i - 1]:
                    symbol = line[i]
                    current_sequence += 1
                    count = max(count, current_sequence)
                else:
                    current_sequence = 1

            if count >= 3 and symbol in self.payouts:
                payout = self.payouts[symbol].get(count, 0)
                total_win += bet * payout

                # Проверка на джекпот
                if symbol == '💰' and count == 5:
                    total_win += self.jackpot
                    is_jackpot = True
                    self.jackpot = 10000  # Сброс джекпота

        return total_win, is_jackpot


class UserManager:
    def __init__(self, data_file="user_data.json"):
        self._locks = defaultdict(asyncio.Lock)
        self._saving = False

        # Инициализируем атрибуты ДО загрузки данных
        self.data_file = data_file
        self.balances = defaultdict(lambda: 1000)
        self.daily_bonuses = defaultdict(lambda: datetime.min)
        self.stats = defaultdict(lambda: {'spins': 0, 'total_bet': 0, 'total_win': 0})
        self.achievements = defaultdict(set)
        self.user_names = defaultdict(str)
        self.user_settings = defaultdict(lambda: {'default_bet': 10})

        # Загружаем данные при инициализации
        self.load_data()

    def load_data(self):
        """Загрузка данных пользователей из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Очищаем defaultdict перед загрузкой
                self.balances.clear()
                self.daily_bonuses.clear()
                self.stats.clear()
                self.user_names.clear()

                # Восстанавливаем балансы
                balances_data = data.get('balances', {})
                for user_id_str, balance in balances_data.items():
                    self.balances[int(user_id_str)] = balance

                # Восстанавливаем даты бонусов
                daily_bonuses_data = data.get('daily_bonuses', {})
                for user_id_str, bonus_date_str in daily_bonuses_data.items():
                    user_id = int(user_id_str)
                    if bonus_date_str and bonus_date_str != "":
                        self.daily_bonuses[user_id] = datetime.fromisoformat(bonus_date_str)
                    else:
                        self.daily_bonuses[user_id] = datetime.min

                # Восстанавливаем статистику
                stats_data = data.get('stats', {})
                for user_id_str, user_stats in stats_data.items():
                    self.stats[int(user_id_str)] = user_stats

                # Восстанавливаем имена пользователей
                user_names_data = data.get('user_names', {})
                for user_id_str, user_name in user_names_data.items():
                    self.user_names[int(user_id_str)] = user_name

                # Восстанавливаем настройки пользователей
                user_settings_data = data.get('user_settings', {})
                for user_id_str, settings in user_settings_data.items():
                    self.user_settings[int(user_id_str)] = settings


                logging.info(f"Данные пользователей загружены из {self.data_file}")
                logging.info(f"Загружено {len(self.balances)} пользователей")

        except Exception as e:
            logging.error(f"Ошибка при загрузке данных: {e}")

    def save_data(self):
        """Сохранение данных пользователей в файл"""
        try:
            # Создаем копии данных для безопасного сохранения
            save_balances = {str(k): v for k, v in self.balances.items()}
            save_stats = {str(k): v for k, v in self.stats.items()}
            save_user_names = {str(k): v for k, v in self.user_names.items()}

            # Обрабатываем даты бонусов
            save_daily_bonuses = {}
            for user_id, bonus_date in self.daily_bonuses.items():
                if bonus_date > datetime.min:
                    save_daily_bonuses[str(user_id)] = bonus_date.isoformat()
                else:
                    save_daily_bonuses[str(user_id)] = ""

            data = {
                'balances': save_balances,
                'daily_bonuses': save_daily_bonuses,
                'stats': save_stats,
                'user_names': save_user_names,
            }

            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(self.data_file) if os.path.dirname(self.data_file) else '.', exist_ok=True)

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logging.info(f"Данные {len(save_balances)} пользователей сохранены в {self.data_file}")

        except Exception as e:
            logging.error(f"Ошибка при сохранении данных: {e}")

    def get_default_bet(self, user_id: int) -> int:
        return self.user_settings[user_id].get('default_bet', 10)

    def set_default_bet(self, user_id: int, bet: int) -> None:
        self.user_settings[user_id]['default_bet'] = bet
        asyncio.create_task(self._delayed_save())

    async def get_balance(self, user_id: int) -> int:
        async with self._locks[user_id]:
            return self.balances[user_id]

    async def update_balance(self, user_id: int, amount: int) -> bool:
        async with self._locks[user_id]:
            if self.balances[user_id] + amount < 0:
                return False
            self.balances[user_id] += amount
            # Откладываем сохранение чтобы не блокировать операцию
            asyncio.create_task(self._delayed_save())
            return True

    async def _delayed_save(self):
        """Отложенное сохранение с дебаунсингом"""
        await asyncio.sleep(1)  # Увеличиваем задержку для группировки операций
        if not self._saving:
            self._saving = True
            try:
                self.save_data()
            finally:
                self._saving = False

    def can_claim_bonus(self, user_id: int) -> bool:
        last_bonus = self.daily_bonuses[user_id]
        return datetime.now() - last_bonus >= timedelta(hours=24)

    def claim_bonus(self, user_id: int) -> int:
        bonus = random.randint(50, 200)
        self.balances[user_id] += bonus
        self.daily_bonuses[user_id] = datetime.now()
        # Откладываем сохранение
        asyncio.create_task(self._delayed_save())
        return bonus


class SlotBot:
    def __init__(self, token: str):
        self.token = token
        self.slot_machine = SlotMachine()
        self.user_manager = UserManager()
        self.app = Application.builder().token(token).build()
        self._spin_queues = defaultdict(asyncio.Queue)
        self._spin_locks = defaultdict(Lock)

        # ДОБАВЛЯЕМ ЗАЩИТУ ОТ ФЛУДА
        self._last_spin_time = defaultdict(float)
        self._min_spin_interval = 5  # Минимальный интервал между спинами в секундах

        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("spin", self.spin))
        self.app.add_handler(CommandHandler("balance", self.balance))
        self.app.add_handler(CommandHandler("bonus", self.bonus))
        self.app.add_handler(CommandHandler("leaderboard", self.leaderboard))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("settings", self.settings))

        self.app.add_handler(CommandHandler("admin", self.admin_stats))
        self.app.add_handler(CommandHandler("addbalance", self.add_balance))
        self.app.add_handler(CommandHandler("users", self.list_users))
        self.app.add_handler(CommandHandler("adminhelp", self.admin_help))
        self.app.add_handler(CommandHandler("broadcast", self.broadcast_message))

        # Add handlers for callback buttons and text messages (only once each)
        self.app.add_handler(CallbackQueryHandler(self.button_handler, pattern="^(spin|bet_|settings|menu)$"))
        self.app.add_handler(CallbackQueryHandler(self.broadcast_confirm_handler, pattern="^broadcast_"))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений для Reply-кнопок"""
        text = update.message.text
        user_id = update.effective_user.id

        if text == "🎰 Крутить":
            bet = self.user_manager.get_default_bet(user_id)
            await self.process_spin_from_text(update, user_id, update.effective_user.first_name, bet)

        elif text == "💰 Баланс":
            await self.balance(update, context)

        elif text == "🎁 Бонус":
            await self.bonus(update, context)

        elif text == "⚙️ Настройки":
            await self.settings(update, context)

        elif text == "🏆 Лидеры":
            await self.leaderboard(update, context)

        elif text == "❓ Помощь":
            await self.help(update, context)

    async def process_spin_from_text(self, update: Update, user_id: int, user_name: str, bet: int):
        """Обработка спина из текстового сообщения"""
        # ДОБАВИТЬ ЭТОТ КОД В НАЧАЛО МЕТОДА:
        current_time = asyncio.get_event_loop().time()
        time_since_last_spin = current_time - self._last_spin_time.get(user_id, 0)

        # Проверяем флуд-контроль
        if time_since_last_spin < self._min_spin_interval:
            wait_time = int(self._min_spin_interval - time_since_last_spin)
            await update.message.reply_text(f"⏳ Слишком часто! Подождите {wait_time} секунд(-ы) перед следующим спином.")
            return

        if self._spin_locks[user_id].locked():
            await update.message.reply_text("⏳ Ваш предыдущий спин еще выполняется! Подождите...")
            return

        async with self._spin_locks[user_id]:
            # Обновляем время последнего спина
            self._last_spin_time[user_id] = current_time

            if not await self.user_manager.update_balance(user_id, -bet):
                await update.message.reply_text("❌ Недостаточно средств на балансе!")
                return

            asyncio.create_task(
                self.process_spin_animation(update, user_id, user_name, bet)
            )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        welcome_text = f"""
    🎰 *ДОБРО ПОЖАЛОВАТЬ В СЛОТ-МАШИНУ, {user_name}!* 🎰

    *🌟 ЧТО НОВОГО В ЭТОЙ ВЕРСИИ:*
    • 🎯 *5 барабанов* с реалистичной анимацией
    • 💰 *Прогрессивный джекпот* который растет с каждой игрой
    • 🎁 *Ежедневный бонус* от 50 до 200 кредитов
    • ⚡ *Быстрые кнопки* для удобной игры
    • 📊 *Подробная статистика* ваших результатов

    *🎮 КАК ИГРАТЬ:*
    1. Используйте кнопку *«🎰 Крутить»* для быстрого старта
    2. Настройте удобную ставку в *«⚙️ Настройки»*
    3. Собирайте комбинации из 3+ одинаковых символов
    4. Получайте *ежедневный бонус* каждый 24 часа

    *💰 ВАШ ТЕКУЩИЙ БАЛАНС:* {await self.user_manager.get_balance(user_id):,} кредитов

    *📋 ДОСТУПНЫЕ КОМАНДЫ:*
    /spin - 🎡 Вращение слотов (можно указать ставку)
    /balance - 💰 Проверить баланс и статистику  
    /bonus - 🎁 Получить ежедневный бонус
    /leaderboard - 🏆 Таблица лидеров
    /settings - ⚙️ Настройки ставок
    /help - ❓ Подробная помощь по игре

    *🎊 УДАЧИ В ИГРЕ!* 🍀
    *Пусть барабаны принесут вам большой выигрыш!* 💫
        """

        keyboard = self.get_main_keyboard()
        await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=keyboard)
    def get_main_keyboard(self):
        """Создает основную клавиатуру с кнопками"""
        keyboard = [
            [KeyboardButton("🎰 Крутить"), KeyboardButton("💰 Баланс")],
            [KeyboardButton("🎁 Бонус"), KeyboardButton("⚙️ Настройки")],
            [KeyboardButton("🏆 Лидеры"), KeyboardButton("❓ Помощь")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_settings_keyboard(self, user_id: int):
        """Создает инлайн клавиатуру для настроек"""
        current_bet = self.user_manager.get_default_bet(user_id)
        keyboard = [
            [
                InlineKeyboardButton("🎰 Крутить", callback_data="spin"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu")
            ],
            [
                InlineKeyboardButton("🔽 1", callback_data="bet_1"),
                InlineKeyboardButton("🔽 5", callback_data="bet_5"),
                InlineKeyboardButton("🔽 10", callback_data="bet_10")
            ],
            [
                InlineKeyboardButton("🔽 25", callback_data="bet_25"),
                InlineKeyboardButton("🔽 50", callback_data="bet_50"),
                InlineKeyboardButton("🔽 100", callback_data="bet_100")
            ],
            [
                InlineKeyboardButton(f"Текущая ставка: {current_bet} 💰", callback_data="current_bet")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_spin_keyboard(self, user_id: int):
        """Создает инлайн клавиатуру для спинов"""
        current_bet = self.user_manager.get_default_bet(user_id)
        keyboard = [
            [
                InlineKeyboardButton("🎰 Крутить снова", callback_data="spin"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
            ],
            [
                InlineKeyboardButton(f"Ставка: {current_bet} 💰", callback_data="current_bet"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на инлайн кнопки"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "spin":
            # Выполняем спин с базовой ставкой
            bet = self.user_manager.get_default_bet(user_id)
            await self.process_spin_from_button(query, user_id, query.from_user.first_name, bet)

        elif data.startswith("bet_"):
            # Изменяем базовую ставку
            new_bet = int(data.split("_")[1])
            self.user_manager.set_default_bet(user_id, new_bet)
            keyboard = self.get_settings_keyboard(user_id)
            await query.edit_message_text(
                f"✅ Базовая ставка изменена на: *{new_bet}* 💰\n\n"
                "Теперь при нажатии '🎰 Крутить' будет использоваться эта ставка.",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        elif data == "settings":
            # Показываем настройки
            current_bet = self.user_manager.get_default_bet(user_id)
            keyboard = self.get_settings_keyboard(user_id)
            await query.edit_message_text(
                f"⚙️ *НАСТРОЙКИ СТАВОК*\n\n"
                f"Текущая базовая ставка: *{current_bet}* 💰\n"
                f"Выберите новую базовую ставку:",
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        elif data == "menu":
            # Возвращаем в главное меню
            welcome_text = """
🎰 *ГЛАВНОЕ МЕНЮ* 🎰

Выберите действие:
"""
            keyboard = self.get_main_keyboard()
            await query.edit_message_text(welcome_text, parse_mode='Markdown')
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Используйте кнопки ниже для управления игрой:",
                reply_markup=keyboard
            )

    async def process_spin_from_button(self, query, user_id: int, user_name: str, bet: int):
        """Обработка спина из кнопки"""
        # ДОБАВИТЬ ЭТОТ КОД В НАЧАЛО МЕТОДА:
        current_time = asyncio.get_event_loop().time()
        time_since_last_spin = current_time - self._last_spin_time.get(user_id, 0)

        # Проверяем флуд-контроль
        if time_since_last_spin < self._min_spin_interval:
            wait_time = int(self._min_spin_interval - time_since_last_spin)
            await query.edit_message_text(f"⏳ Слишком часто! Подождите {wait_time} секунд(-ы) перед следующим спином.")
            return

        if self._spin_locks[user_id].locked():
            await query.edit_message_text("⏳ Ваш предыдущий спин еще выполняется! Подождите...")
            return

        async with self._spin_locks[user_id]:
            # Обновляем время последнего спина
            self._last_spin_time[user_id] = current_time

            if not await self.user_manager.update_balance(user_id, -bet):
                await query.edit_message_text("❌ Недостаточно средств на балансе!")
                return

            # Запускаем анимацию спина
            await self.process_spin_animation_from_button(query, user_id, user_name, bet)

    async def process_spin_animation_from_button(self, query, user_id: int, user_name: str, bet: int):
        """Анимация спина для кнопочного вызова с защитой от флуд-контроля"""
        try:
            message = query.message

            # Сохраняем имя пользователя
            self.user_manager.user_names[user_id] = user_name

            # Выполняем спин
            reels, win_amount, is_jackpot = self.slot_machine.spin(bet)

            # УПРОЩЕННАЯ АНИМАЦИЯ
            display_reels = [['⚫' for _ in range(3)] for _ in range(5)]

            # Анимация по столбцам справа налево
            for col in range(5):  # 5 столбцов (барабанов)
                for row in range(3):  # 3 строки в каждом барабане
                    display_reels[col][row] = reels[col][row]

                reel_display = self.format_reels(display_reels)
                try:
                    await message.edit_text(
                        f"🎰 *ВРАЩЕНИЕ БАРАБАНОВ...*\n\n{reel_display}",
                        reply_markup=None
                    )
                    await asyncio.sleep(0.7)
                except Exception as e:
                    logging.warning(f"Flood control in button animation: {e}")
                    break

            # Финальный результат
            final_display = self.format_reels(reels)
            result_text = f"🎰 *РЕЗУЛЬТАТ ВРАЩЕНИЯ*\nИгрок: {user_name}\nСтавка: {bet} 💰\n\n{final_display}\n"

            if win_amount > 0:
                await self.user_manager.update_balance(user_id, win_amount)
                self.user_manager.stats[user_id]['total_win'] += win_amount

                if is_jackpot:
                    result_text += f"\n🎉 *ДЖЕКПОТ!* 🎉\n🏆 ВЫ ВЫИГРАЛИ ДЖЕКПОТ!\n💰 Выигрыш: {win_amount} кредитов!"
                    await self.animate_jackpot(message, result_text)
                elif win_amount > bet * 10:
                    result_text += f"\n🎊 *БОЛЬШОЙ ВЫИГРЫШ!* 🎊\n💰 Выигрыш: {win_amount} кредитов!"
                    await self.animate_big_win(message, result_text)
                else:
                    result_text += f"\n🎉 *ВЫ ВЫИГРАЛИ!* 🎉\n💰 Выигрыш: {win_amount} кредитов!"
                    # Упрощенная анимация для маленьких выигрышей
                    await message.edit_text(result_text, parse_mode='Markdown')
            else:
                result_text += "\n😔 *ПОВЕЗЕТ В СЛЕДУЮЩИЙ РАЗ!*"
                await message.edit_text(result_text, parse_mode='Markdown')

            # Обновление статистики
            self.user_manager.stats[user_id]['spins'] += 1
            self.user_manager.stats[user_id]['total_bet'] += bet

            # Сохраняем данные
            asyncio.create_task(self.user_manager._delayed_save())

            result_text += f"\n\n💳 Новый баланс: {await self.user_manager.get_balance(user_id):,} 💰"
            result_text += f"\n🎯 Прогрессивный джекпот: {self.slot_machine.jackpot:,} 💰"

            # Показываем результат с кнопками
            keyboard = self.get_spin_keyboard(user_id)
            await message.edit_text(result_text, parse_mode='Markdown', reply_markup=keyboard)


        except Exception as e:

            logging.error(f"Error in button spin animation for user {user_id}: {e}")

            await self.user_manager.update_balance(user_id, bet)

            try:

                await query.edit_message_text("❌ Произошла ошибка при вращении! Ставка возвращена.")

            except Exception as e2:

                logging.error(f"Could not send error message: {e2}")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает настройки ставок"""
        user_id = update.effective_user.id
        current_bet = self.user_manager.get_default_bet(user_id)

        settings_text = f"""
⚙️ *НАСТРОЙКИ СТАВОК*

Текущая базовая ставка: *{current_bet}* 💰
Баланс: *{await self.user_manager.get_balance(user_id):,}* 💰

Выберите новую базовую ставку:
• Меньшие ставки - дольше игра
• Большие ставки - больше выигрыши
        """

        keyboard = self.get_settings_keyboard(user_id)
        await update.message.reply_text(settings_text, parse_mode='Markdown', reply_markup=keyboard)

    # Обновляем команду spin для использования базовой ставки
    async def spin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        # Используем базовую ставку если не указана явно
        try:
            bet = int(context.args[0]) if context.args else self.user_manager.get_default_bet(user_id)
        except:
            bet = self.user_manager.get_default_bet(user_id)

        if bet < 1:
            await update.message.reply_text("❌ Ставка должна быть положительной!")
            return

        # ДОБАВИТЬ ЭТОТ КОД ПЕРЕД ПРОВЕРКОЙ _spin_locks:
        current_time = asyncio.get_event_loop().time()
        time_since_last_spin = current_time - self._last_spin_time.get(user_id, 0)

        # Проверяем флуд-контроль
        if time_since_last_spin < self._min_spin_interval:
            wait_time = int(self._min_spin_interval - time_since_last_spin)
            await update.message.reply_text(f"⏳ Слишком часто! Подождите {wait_time} секунд(-ы) перед следующим спином.")
            return

        if self._spin_locks[user_id].locked():
            await update.message.reply_text("⏳ Ваш предыдущий спин еще выполняется! Подождите...")
            return

        async with self._spin_locks[user_id]:
            # Обновляем время последнего спина
            self._last_spin_time[user_id] = current_time

            if not await self.user_manager.update_balance(user_id, -bet):
                await update.message.reply_text("❌ Недостаточно средств на балансе!")
                return

            asyncio.create_task(
                self.process_spin_animation(update, user_id, user_name, bet)
            )

    async def process_spin_animation(self, update: Update, user_id: int, user_name: str, bet: int):
        """Обработка анимации в отдельной задаче с защитой от флуд-контроля"""
        try:
            message = await update.message.reply_text(
                "🎰 *НАЧИНАЕМ ВРАЩЕНИЕ!*\n\n🔄 Подготовка барабанов...",
                parse_mode='Markdown'
            )

            # Сохраняем имя пользователя
            self.user_manager.user_names[user_id] = user_name

            # Выполняем спин
            reels, win_amount, is_jackpot = self.slot_machine.spin(bet)

            # УПРОЩЕННАЯ АНИМАЦИЯ - меньше сообщений
            display_reels = [['⚫' for _ in range(3)] for _ in range(5)]

            # Анимация по столбцам справа налево
            for col in range(5):  # 5 столбцов (барабанов)
                for row in range(3):  # 3 строки в каждом барабане
                    display_reels[col][row] = reels[col][row]

                reel_display = self.format_reels(display_reels)
                try:
                    await message.edit_text(f"🎰 *ВРАЩЕНИЕ БАРАБАНОВ...*\n\n{reel_display}")
                    await asyncio.sleep(0.7)  # Увеличиваем задержку
                except Exception as e:
                    logging.warning(f"Flood control during animation: {e}")
                    # Продолжаем без анимации если сработал флуд-контроль
                    break

            # Финальный результат
            final_display = self.format_reels(reels)
            result_text = f"🎰 *РЕЗУЛЬТАТ ВРАЩЕНИЯ*\nИгрок: {user_name}\nСтавка: {bet} 💰\n\n{final_display}\n"

            if win_amount > 0:
                await self.user_manager.update_balance(user_id, win_amount)
                self.user_manager.stats[user_id]['total_win'] += win_amount

                if is_jackpot:
                    result_text += f"\n🎉 *ДЖЕКПОТ!* 🎉\n🏆 ВЫ ВЫИГРАЛИ ДЖЕКПОТ!\n💰 Выигрыш: {win_amount} кредитов!"
                    # Упрощенная анимация джекпота
                    try:
                        await self.animate_jackpot_simple(message, result_text)
                    except Exception as e:
                        logging.warning(f"Flood control in jackpot animation: {e}")
                        await message.edit_text(result_text, parse_mode='Markdown')
                elif win_amount > bet * 10:
                    result_text += f"\n🎊 *БОЛЬШОЙ ВЫИГРЫШ!* 🎊\n💰 Выигрыш: {win_amount} кредитов!"
                    await message.edit_text(result_text, parse_mode='Markdown')
                else:
                    result_text += f"\n🎉 *ВЫ ВЫИГРАЛИ!* 🎉\n💰 Выигрыш: {win_amount} кредитов!"
                    await message.edit_text(result_text, parse_mode='Markdown')
            else:
                result_text += "\n😔 *ПОВЕЗЕТ В СЛЕДУЮЩИЙ РАЗ!*"
                await message.edit_text(result_text, parse_mode='Markdown')

            # Обновление статистики
            self.user_manager.stats[user_id]['spins'] += 1
            self.user_manager.stats[user_id]['total_bet'] += bet

            # Сохраняем данные
            asyncio.create_task(self.user_manager._delayed_save())

            result_text += f"\n\n💳 Новый баланс: {await self.user_manager.get_balance(user_id):,} 💰"
            result_text += f"\n🎯 Прогрессивный джекпот: {self.slot_machine.jackpot:,} 💰"

            # Финальное сообщение с кнопками
            keyboard = self.get_spin_keyboard(user_id)
            try:
                await message.edit_text(result_text, parse_mode='Markdown', reply_markup=keyboard)
            except Exception as e:
                logging.warning(f"Flood control for final message: {e}")
                # Если не удалось отредактировать, отправляем новое сообщение
                await update.message.reply_text(result_text, parse_mode='Markdown', reply_markup=keyboard)

        except Exception as e:
            logging.error(f"Error in spin animation for user {user_id}: {e}")
            # Возвращаем ставку в случае ошибки
            await self.user_manager.update_balance(user_id, bet)
            try:
                await update.message.reply_text("❌ Произошла ошибка при вращении! Ставка возвращена.")
            except Exception as e2:
                logging.error(f"Could not send error message: {e2}")

    async def animate_jackpot_simple(self, message, base_text: str):
        """Упрощенная анимация джекпота (меньше сообщений)"""
        try:
            # Всего 2 кадра вместо 3
            jackpot_frames = [
                "🎆✨🎇🌠🎆✨🎇🌠",
                "💰🎉🏆🎊💰🎉🏆🎊"
            ]

            for frame in jackpot_frames:
                await message.edit_text(f"{base_text}\n\n{frame}")
                await asyncio.sleep(1.0)  # Увеличиваем задержку
        except Exception as e:
            logging.warning(f"Flood control in simplified jackpot: {e}")
            # Если сработал флуд-контроль, просто показываем финальный результат
            await message.edit_text(base_text, parse_mode='Markdown')

    async def animate_big_win(self, message, base_text: str):
        for _ in range(3):
            await message.edit_text(f"{base_text}\n\n✨ 💰 ✨")
            await asyncio.sleep(0.3)
            await message.edit_text(f"{base_text}\n\n💰 ✨ 💰")
            await asyncio.sleep(0.3)

    async def animate_small_win(self, message, base_text: str):
        for _ in range(2):
            await message.edit_text(f"{base_text}\n\n✨")
            await asyncio.sleep(0.3)
            await message.edit_text(f"{base_text}\n\n🌟")
            await asyncio.sleep(0.3)

    def format_reels(self, reels: List[List[str]]) -> str:
        """Форматирование барабанов для отображения"""
        lines = []
        for i in range(3):
            line = " ".join(reels[j][i] for j in range(5))
            lines.append(line)
        return "\n".join(lines)

    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        balance = await self.user_manager.get_balance(user_id)  # Add await here
        stats = self.user_manager.stats[user_id]

        balance_text = f"""
    💳 *ВАШ БАЛАНС*

    💰 Текущий баланс: {balance:,} кредитов
    🎯 Всего спинов: {stats['spins']}
    📊 Общая ставка: {stats['total_bet']:,}
    🎊 Общий выигрыш: {stats['total_win']:,}

    📈 Прогрессивный джекпот: {self.slot_machine.jackpot:,} 💰
        """

        await update.message.reply_text(balance_text, parse_mode='Markdown')

    async def bonus(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not self.user_manager.can_claim_bonus(user_id):
            next_bonus = self.user_manager.daily_bonuses[user_id] + timedelta(hours=24)
            wait_time = next_bonus - datetime.now()
            hours = int(wait_time.total_seconds() // 3600)
            minutes = int((wait_time.total_seconds() % 3600) // 60)

            await update.message.reply_text(
                f"❌ Вы уже получали бонус сегодня!\n"
                f"⏰ Следующий бонус через: {hours}ч {minutes}м"
            )
            return

        bonus = self.user_manager.claim_bonus(user_id)
        new_balance = await self.user_manager.get_balance(user_id)

        bonus_text = f"""
🎁 *ЕЖЕДНЕВНЫЙ БОНУС*

💰 Вы получили: {bonus} кредитов
💳 Новый баланс: {new_balance:,} кредитов

🔄 Следующий бонус через 24 часа!
        """

        await update.message.reply_text(bonus_text, parse_mode='Markdown')

    async def add_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления/списания баланса пользователю (только для администратора)"""
        user_id = update.effective_user.id

        # ЗАМЕНИТЕ НА ВАШ TELEGRAM ID
        ADMIN_IDS = [2120805605,913052916]  # Ваши ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        # Проверяем аргументы команды
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "ℹ️ Использование команды:\n"
                "`/addbalance <user_id> <amount>`\n\n"
                "Примеры:\n"
                "`/addbalance 123456789 1000` - добавить 1000 кредитов\n"
                "`/addbalance 123456789 -500` - списать 500 кредитов\n"
                "`/addbalance 123456789 0` - установить баланс в 0"
            )
            return

        try:
            target_user_id = int(context.args[0])
            amount = int(context.args[1])

            # Проверяем, существует ли пользователь
            if target_user_id not in self.user_manager.balances:
                await update.message.reply_text("❌ Пользователь не найден!")
                return

            current_balance = await self.user_manager.get_balance(target_user_id)
            target_user_name = self.user_manager.user_names.get(target_user_id, "Неизвестный пользователь")

            # Особый случай: amount = 0 (установить баланс в 0)
            if amount == 0:
                # Вычисляем сколько нужно списать, чтобы баланс стал 0
                amount_to_zero = -current_balance
                success = await self.user_manager.update_balance(target_user_id, amount_to_zero)

                if success:
                    admin_message = (
                        f"✅ Баланс обнулен!\n\n"
                        f"👤 Пользователь: {target_user_name} (ID: {target_user_id})\n"
                        f"💰 Предыдущий баланс: {current_balance:,} кредитов\n"
                        f"💳 Новый баланс: 0 кредитов\n"
                        f"📉 Списано: {abs(amount_to_zero):,} кредитов"
                    )
                    await update.message.reply_text(admin_message)
                    logging.info(f"ADMIN: User {user_id} reset balance to 0 for user {target_user_id}")
                else:
                    await update.message.reply_text("❌ Ошибка при обнулении баланса!")
                return

            # Для положительных и отрицательных сумм
            if amount > 0:
                # Добавление баланса
                success = await self.user_manager.update_balance(target_user_id, amount)
                if success:
                    new_balance = await self.user_manager.get_balance(target_user_id)
                    admin_message = (
                        f"✅ Баланс пополнен!\n\n"
                        f"👤 Пользователь: {target_user_name} (ID: {target_user_id})\n"
                        f"💰 Добавлено: {amount:,} кредитов\n"
                        f"💳 Предыдущий баланс: {current_balance:,} кредитов\n"
                        f"💳 Новый баланс: {new_balance:,} кредитов"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка при пополнении баланса!")
                    return

            else:  # amount < 0 (списание)
                # Проверяем, достаточно ли средств для списания
                if current_balance + amount < 0:
                    await update.message.reply_text(
                        f"❌ Недостаточно средств для списания!\n"
                        f"💰 Текущий баланс: {current_balance:,} кредитов\n"
                        f"💸 Запрошено списание: {abs(amount):,} кредитов\n"
                        f"📉 Не хватает: {abs(current_balance + amount):,} кредитов"
                    )
                    return

                success = await self.user_manager.update_balance(target_user_id, amount)
                if success:
                    new_balance = await self.user_manager.get_balance(target_user_id)
                    admin_message = (
                        f"✅ Баланс списан!\n\n"
                        f"👤 Пользователь: {target_user_name} (ID: {target_user_id})\n"
                        f"💸 Списано: {abs(amount):,} кредитов\n"
                        f"💳 Предыдущий баланс: {current_balance:,} кредитов\n"
                        f"💳 Новый баланс: {new_balance:,} кредитов"
                    )
                else:
                    await update.message.reply_text("❌ Ошибка при списании баланса!")
                    return

            await update.message.reply_text(admin_message)

            # Логируем действие
            action_type = "пополнение" if amount > 0 else "списание"
            logging.info(
                f"ADMIN: User {user_id} {action_type} {abs(amount)} for user {target_user_id}. New balance: {new_balance}")

        except ValueError:
            await update.message.reply_text("❌ Неверный формат аргументов! Используйте числа.")
        except Exception as e:
            logging.error(f"Ошибка в add_balance: {e}")
            await update.message.reply_text("❌ Произошла ошибка при выполнении команды!")

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Компактный список игроков (только ID, имя, прокруты)"""
        user_id = update.effective_user.id

        ADMIN_IDS = [2120805605,913052916]  # Ваши Telegram ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        try:
            if not self.user_manager.balances:
                await update.message.reply_text("📭 Нет зарегистрированных пользователей.")
                return

            # Сортируем по количеству прокрутов
            users_sorted = sorted(
                [(uid, self.user_manager.stats.get(uid, {'spins': 0})['spins'])
                 for uid in self.user_manager.balances.keys()],
                key=lambda x: x[1],
                reverse=True
            )

            users_text = "👥 *СПИСОК ИГРОКОВ*\n\n"

            for i, (user_id, spins) in enumerate(users_sorted[:50], 1):  # Показываем топ-50 по прокрутам
                user_name = self.user_manager.user_names.get(user_id, "Неизвестный")

                # Обрезаем длинные имена
                if len(user_name) > 12:
                    user_name = user_name[:12] + "..."

                users_text += f"{i:2d}. `{user_id}` - {user_name} - *{spins}* 🎰\n"

            users_text += f"\n👥 *Всего пользователей:* {len(users_sorted)}"
            users_text += f"\n🎰 *Всего прокрутов:* {sum(stats['spins'] for stats in self.user_manager.stats.values())}"

            await update.message.reply_text(users_text, parse_mode='Markdown')

        except Exception as e:
            logging.error(f"Ошибка в list_users: {e}")
            await update.message.reply_text("❌ Произошла ошибка при получении списка пользователей!")


    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Создаем простую таблицу лидеров по балансу
        users_balances = [(uid, bal) for uid, bal in self.user_manager.balances.items()]
        users_balances.sort(key=lambda x: x[1], reverse=True)

        leaderboard_text = "🏆 *ТАБЛИЦА ЛИДЕРОВ*\n\n"

        for i, (user_id, balance) in enumerate(users_balances[:10], 1):
            leaderboard_text += f"{i}. 🎯 Игрок #{self.user_manager.user_names[user_id]}: {balance:,} 💰\n"

        leaderboard_text += f"\n🎯 Прогрессивный джекпот: {self.slot_machine.jackpot:,} 💰"

        await update.message.reply_text(leaderboard_text, parse_mode='Markdown')

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
    🎰 *ПОМОЩЬ ПО ИГРЕ СЛОТ-МАШИНА* 🎰

    *🏠 ОСНОВНЫЕ КОМАНДЫ:*
    /spin [ставка] - 🎡 Запуск слотов (по умолчанию используется ваша базовая ставка)
    /balance - 💰 Показать баланс и статистику
    /bonus - 🎁 Получить ежедневный бонус (50-200 кредитов)
    /leaderboard - 🏆 Таблица лидеров по балансу
    /settings - ⚙️ Настройка базовой ставки

    *🎯 УПРАВЛЕНИЕ ЧЕРЕЗ КНОПКИ:*
    • «🎰 Крутить» - быстрый спин с базовой ставкой
    • «💰 Баланс» - посмотреть свой баланс
    • «🎁 Бонус» - получить ежедневный бонус
    • «⚙️ Настройки» - изменить базовую ставку
    • «🏆 Лидеры» - таблица лидеров
    • «❓ Помощь» - эта справка

    *🎮 ПРАВИЛА ИГРЫ:*
    • *5 барабанов, 5 линий выплат* (3 горизонтальные + 2 диагональные)
    • Выигрышные комбинации от 3+ одинаковых символов подряд
    • Символ 💰 дает самый большой выигрыш и джекпот!
    • *Прогрессивный джекпот* растет с каждой игрой

    *💰 СИМВОЛЫ И ВЫПЛАТЫ (умножаются на вашу ставку):*
    🍒 3x=×2, 4x=×5, 5x=×10
    🍋 3x=×3, 4x=×8, 5x=×15  
    🍊 3x=×4, 4x=×10, 5x=×20
    🍇 3x=×5, 4x=×15, 5x=×30
    🍌 3x=×8, 4x=×20, 5x=×50
    ⭐ 3x=×10, 4x=×25, 5x=×75
    💎 3x=×15, 4x=×40, 5x=×100
    7️⃣ 3x=×20, 4x=×50, 5x=×150
    💰 3x=×50, 4x=×200, 5x=×1000 + *ДЖЕКПОТ!*

    *🎊 ОСОБЫЕ ВОЗМОЖНОСТИ:*
    • *Ежедневный бонус* - каждый 24 часа
    • *Настройка ставки* - установите удобную базовую ставку
    • *Анимации* - специальные эффекты для больших выигрышей
    • *Статистика* - отслеживайте свою игровую активность

    *💡 СОВЕТЫ:*
    • Начните с небольших ставок для знакомства с игрой
    • Используйте /settings для удобной настройки ставок
    • Не забывайте забирать ежедневный бонус!
    • Следите за прогрессивным джекпотом

    *Удачи в игре! 🍀*
        """

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def admin_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Справка по административным командам"""
        user_id = update.effective_user.id

        # Список ID администраторов - должен совпадать с другими админ-функциями
        ADMIN_IDS = [2120805605,913052916]  # Ваши Telegram ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        help_text = """
    🔧 *АДМИНИСТРАТИВНЫЕ КОМАНДЫ*

    *Статистика и мониторинг:*
    /admin - 📊 Общая статистика бота
    /users - 👥 Список игроков (ID, имя, прокруты)
    /leaderboard - 🏆 Таблица лидеров

    *Управление балансами:*
    /addbalance - 💰 Управление балансом пользователя

    *Использование /addbalance:*
    `/addbalance <user_id> <amount>`
    
    *Рассылка сообщений:*
    `/broadcast - 📢 Отправка сообщения всем пользователям`
    
    *Использование /broadcast:*
    `/broadcast <текст сообщения>`

    *Примеры:*
    • `/addbalance 123456789 1000` - добавить 1000 кредитов
    • `/addbalance 123456789 -500` - списать 500 кредитов  
    • `/addbalance 123456789 0` - обнулить баланс

    *Параметры:*
    • `user_id` - ID пользователя в Telegram
    • `amount` - сумма (положительная - пополнение, отрицательная - списание, 0 - обнуление)

    *Примечания:*
    • Все изменения баланса логируются
    • Проверяйте ID пользователя через /users
    • При списании проверяется достаточность средств
    • Джекпот автоматически растет с каждой игрой
        """

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика для администратора"""
        user_id = update.effective_user.id

        # Список ID администраторов - ЗАМЕНИТЕ на свои ID
        ADMIN_IDS = [2120805605,913052916]  # Ваши Telegram ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        try:
            total_users = len(self.user_manager.balances)
            total_balance = sum(self.user_manager.balances.values())
            total_spins = sum(stats['spins'] for stats in self.user_manager.stats.values())
            total_bet = sum(stats['total_bet'] for stats in self.user_manager.stats.values())
            total_win = sum(stats['total_win'] for stats in self.user_manager.stats.values())

            # Активные пользователи (кто делал хотя бы 1 спин)
            active_users = sum(1 for stats in self.user_manager.stats.values() if stats['spins'] > 0)

            # Топ-5 пользователей по балансу
            top_users = sorted(
                [(uid, bal) for uid, bal in self.user_manager.balances.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]

            stats_text = f"""
    📊 *АДМИН СТАТИСТИКА*

    👥 Всего пользователей: {total_users}
    🎯 Активных пользователей: {active_users}
    💰 Общий баланс системы: {total_balance:,} 💰

    🎰 Игровая статистика:
    • Всего спинов: {total_spins:,}
    • Общая сумма ставок: {total_bet:,} 💰
    • Общая сумма выигрышей: {total_win:,} 💰
    • Доход казино: {total_bet - total_win:,} 💰

    🏆 Текущий джекпот: {self.slot_machine.jackpot:,} 💰

    📈 Топ-5 игроков:
    """

            for i, (user_id, balance) in enumerate(top_users, 1):
                user_name = self.user_manager.user_names.get(user_id, f"Игрок #{user_id}")
                stats_text += f"{i}. {user_name}: {balance:,} 💰\n"

            # Добавляем информацию о файле данных
            import os
            if os.path.exists(self.user_manager.data_file):
                file_size = os.path.getsize(self.user_manager.data_file)
                stats_text += f"\n💾 Размер файла данных: {file_size / 1024:.1f} KB"

            await update.message.reply_text(stats_text, parse_mode='Markdown')

        except Exception as e:
            logging.error(f"Ошибка в admin_stats: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики!")

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправка сообщения всем пользователям (только для администратора)"""
        user_id = update.effective_user.id

        ADMIN_IDS = [2120805605]  # Ваши Telegram ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        # Проверяем аргументы команды
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Использование команды:\n"
                "`/broadcast <сообщение>`\n\n"
                "Пример:\n"
                "`/broadcast Всем привет! Новое обновление бота!`\n\n"
                "⚠️ Сообщение будет отправлено всем пользователям бота."
            )
            return

        message_text = " ".join(context.args)

        # Подтверждение перед рассылкой
        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, отправить", callback_data=f"broadcast_confirm_{hash(message_text)}"),
                InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")
            ]
        ])

        await update.message.reply_text(
            f"📢 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
            f"Сообщение:\n{message_text}\n\n"
            f"Получателей: {len(self.user_manager.balances)} пользователей\n\n"
            f"Вы уверены, что хотите отправить это сообщение всем пользователям?",
            parse_mode='Markdown',
            reply_markup=confirm_keyboard
        )

    async def broadcast_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик подтверждения рассылки"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        ADMIN_IDS = [2120805605]

        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Доступ запрещен!")
            return

        if data == "broadcast_cancel":
            await query.edit_message_text("❌ Рассылка отменена.")
            return

        if data.startswith("broadcast_confirm_"):
            # Извлекаем хэш сообщения из callback_data
            message_hash = int(data.split("_")[2])

            # Находим оригинальное сообщение в истории
            original_text = query.message.text
            message_lines = original_text.split('\n')
            message_text = '\n'.join(message_lines[4:-3])  # Извлекаем текст сообщения

            # Проверяем хэш для безопасности
            if hash(message_text) != message_hash:
                await query.edit_message_text("❌ Ошибка: сообщение не совпадает!")
                return

            await self.execute_broadcast(query, message_text, context)

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправка сообщения всем пользователям (только для администратора)"""
        user_id = update.effective_user.id

        ADMIN_IDS = [2120805605]  # Ваши Telegram ID

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Доступ запрещен!")
            return

        # Проверяем аргументы команды
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Использование команды:\n"
                "`/broadcast <сообщение>`\n\n"
                "Пример:\n"
                "`/broadcast Всем привет! Новое обновление бота!`\n\n"
                "⚠️ Сообщение будет отправлено всем пользователям бота."
            )
            return

        message_text = " ".join(context.args)

        # Подтверждение перед рассылкой
        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, отправить", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")
            ]
        ])

        # Сохраняем текст сообщения в контексте для последующего использования
        context.user_data['broadcast_message'] = message_text

        await update.message.reply_text(
            f"📢 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
            f"Сообщение:\n{message_text}\n\n"
            f"Получателей: {len(self.user_manager.balances)} пользователей\n\n"
            f"Вы уверены, что хотите отправить это сообщение всем пользователям?",
            parse_mode='Markdown',
            reply_markup=confirm_keyboard
        )

    async def broadcast_confirm_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик подтверждения рассылки"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        ADMIN_IDS = [2120805605]

        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Доступ запрещен!")
            return

        if data == "broadcast_cancel":
            await query.edit_message_text("❌ Рассылка отменена.")
            return

        if data == "broadcast_confirm":
            # Получаем сохраненное сообщение из контекста
            message_text = context.user_data.get('broadcast_message', '')

            if not message_text:
                await query.edit_message_text("❌ Ошибка: текст сообщения не найден!")
                return

            await self.execute_broadcast(query, message_text, context)

    async def execute_broadcast(self, query, message_text: str, context: ContextTypes.DEFAULT_TYPE):
        """Выполнение рассылки сообщения всем пользователям"""
        try:
            await query.edit_message_text("🔄 Начинаем рассылку сообщения...")

            total_users = len(self.user_manager.balances)
            successful_sends = 0
            failed_sends = 0
            failed_users = []

            broadcast_text = f"📢 *ОБЪЯВЛЕНИЕ ОТ АДМИНИСТРАЦИИ*\n\n{message_text}\n\n"

            # Рассылка всем пользователям
            for user_id in list(self.user_manager.balances.keys()):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=broadcast_text,
                        parse_mode='Markdown'
                    )
                    successful_sends += 1

                    # Небольшая задержка чтобы не превысить лимиты Telegram
                    if successful_sends % 10 == 0:
                        await asyncio.sleep(0.5)

                except Exception as e:
                    failed_sends += 1
                    failed_users.append(user_id)
                    logging.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

            # Статистика рассылки
            result_text = (
                f"📊 *РЕЗУЛЬТАТ РАССЫЛКИ*\n\n"
                f"✅ Успешно отправлено: {successful_sends}/{total_users}\n"
                f"❌ Не удалось отправить: {failed_sends}/{total_users}\n"
                f"📨 Текст сообщения:\n{message_text}"
            )

            if failed_users:
                result_text += f"\n\n⚠️ Не отправлено пользователям: {', '.join(map(str, failed_users[:10]))}"
                if len(failed_users) > 10:
                    result_text += f" ... и еще {len(failed_users) - 10}"

            await query.edit_message_text(result_text, parse_mode='Markdown')

            # Очищаем сохраненное сообщение
            if 'broadcast_message' in context.user_data:
                del context.user_data['broadcast_message']

            # Логируем действие
            logging.info(
                f"ADMIN: User {query.from_user.id} sent broadcast to {successful_sends} users. Message: {message_text}")

        except Exception as e:
            logging.error(f"Ошибка при выполнении рассылки: {e}")
            await query.edit_message_text(f"❌ Произошла ошибка при рассылке: {e}")

    def run(self):
        """Запуск бота"""
        print("🎰 Слот-бот запущен!")
        try:
            self.app.run_polling()
        except KeyboardInterrupt:
            print("\nСохранение данных перед завершением...")
            self.user_manager.save_data()
            print("Данные сохранены. До свидания!")


# Запуск бота

if __name__ == "__main__":
    TOKEN = "8018546111:AAGZ7nh7CcsrTlIAq7NJ_vEcmKlhFNzYBY4"  # Замените на ваш токен
    bot = SlotBot(TOKEN)
    bot.run()
