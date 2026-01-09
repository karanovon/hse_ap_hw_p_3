import logging
import os
import sys
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

if os.getenv('RENDER') is None:
    load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENWEATHER_TOKEN = os.getenv('OPENWEATHER_TOKEN')

logger = logging.getLogger(__name__)

bot = TeleBot(token=TELEGRAM_TOKEN)

users = {}
user_states = {}


def check_tokens():
    """Проверяет наличие обязательных токенов."""
    if not TELEGRAM_TOKEN:
        logger.critical('Отсутствует TELEGRAM_TOKEN')
        return False
    return True


def get_weather(city):
    """Получает текущую температуру в городе через OpenWeather API."""
    if not OPENWEATHER_TOKEN:
        logger.warning('OPENWEATHER_TOKEN не задан, используется 0 градусов')
        return 0

    url = 'https://api.openweathermap.org/data/2.5/weather'
    params = {
        'q': city,
        'appid': OPENWEATHER_TOKEN,
        'units': 'metric',
        'lang': 'ru',
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != HTTPStatus.OK:
            logger.warning(
                'Ошибка получения погоды: %s, город=%s',
                response.status_code,
                city
            )
            return 0

        data = response.json()
        return data['main']['temp']

    except requests.RequestException as error:
        logger.error('Ошибка запроса погоды: %s', error)
        return 0


def calculate_water_goal(user):
    """Рассчитывает дневную норму воды."""
    temperature = get_weather(user['city'])

    base = user['weight'] * 30
    activity_bonus = (user['activity'] // 30) * 500
    weather_bonus = 500 if temperature > 25 else 0

    return base + activity_bonus + weather_bonus


def calculate_calorie_goal(user):
    """Рассчитывает дневную норму калорий."""
    bmr = (
        10 * user['weight']
        + 6.25 * user['height']
        - 5 * user['age']
    )
    activity_bonus = 300 if user['activity'] >= 30 else 150
    return int(bmr + activity_bonus)


def get_food_info(product_name):
    """Получает информацию о продукте через OpenFoodFacts."""
    url = (
        'https://world.openfoodfacts.org/cgi/search.pl'
        f'?action=process&search_terms={product_name}&json=true'
    )

    response = requests.get(url)
    if response.status_code != HTTPStatus.OK:
        return None

    data = response.json()
    products = data.get('products', [])

    if not products:
        return None

    product = products[0]
    return {
        'name': product.get('product_name', 'Неизвестно'),
        'calories': product.get('nutriments', {})
        .get('energy-kcal_100g', 0),
    }


@bot.message_handler(commands=['start'])
def start(message):
    logger.info('Команда /start от пользователя %s', message.chat.id)
    bot.send_message(
        message.chat.id,
        'Используйте команду /set_profile для начала.'
    )


@bot.message_handler(commands=['set_profile'])
def set_profile(message):
    logger.info('Команда /set_profile от пользователя %s', message.chat.id)
    user_states[message.chat.id] = {'step': 'weight'}
    users[message.chat.id] = {
        'logged_water': 0,
        'logged_calories': 0,
        'burned_calories': 0,
    }
    bot.send_message(message.chat.id, 'Введите ваш вес (кг):')


@bot.message_handler(func=lambda message: message.chat.id in user_states)
def handle_profile(message):
    state = user_states[message.chat.id]
    user = users[message.chat.id]

    logger.info(
        'Профиль step=%s от пользователя %s: %s',
        state["step"],
        message.chat.id,
        message.text
    )

    try:
        if state['step'] == 'weight':
            user['weight'] = float(message.text)
            state['step'] = 'height'
            bot.send_message(message.chat.id, 'Введите рост (см):')

        elif state['step'] == 'height':
            user['height'] = float(message.text)
            state['step'] = 'age'
            bot.send_message(message.chat.id, 'Введите возраст:')

        elif state['step'] == 'age':
            user['age'] = int(message.text)
            state['step'] = 'activity'
            bot.send_message(
                message.chat.id,
                'Сколько минут активности у вас в день?'
            )

        elif state['step'] == 'activity':
            user['activity'] = int(message.text)
            state['step'] = 'city'
            bot.send_message(message.chat.id, 'Введите город:')

        elif state['step'] == 'city':
            user['city'] = message.text

            temperature = get_weather(user['city'])

            user['water_goal'] = calculate_water_goal(user)
            user['calorie_goal'] = calculate_calorie_goal(user)

            user_states.pop(message.chat.id)

            weather_info = (
                f'Текущая температура в городе {user["city"]}: '
                f'{temperature} °C\n'
                if temperature != 0
                else 'Не удалось получить данные о погоде.\n'
            )

            heat_info = (
                'Из-за жаркой погоды норма воды была увеличена.\n'
                if temperature > 25
                else ''
            )

            bot.send_message(
                message.chat.id,
                'Профиль успешно сохранён.\n\n'
                f'{weather_info}'
                f'{heat_info}\n'
                f'Норма воды: {user["water_goal"]} мл\n'
                f'Норма калорий: {user["calorie_goal"]} ккал'
            )

    except ValueError:
        bot.send_message(
            message.chat.id,
            'Ошибка ввода. Пожалуйста, введите корректное число.'
        )


@bot.message_handler(commands=['log_water'])
def log_water(message):
    logger.info(
        'Команда /log_water от пользователя %s: %s',
        message.chat.id,
        message.text
    )
    user = users.get(message.chat.id)
    if not user:
        bot.send_message(
            message.chat.id,
            'Сначала необходимо настроить профиль.'
        )
        return

    try:
        amount = int(message.text.split()[1])
        user['logged_water'] += amount
        remaining = user['water_goal'] - user['logged_water']

        bot.send_message(
            message.chat.id,
            f'Записано {amount} мл воды.\n'
            f'Осталось: {max(remaining, 0)} мл.'
        )
    except (IndexError, ValueError):
        bot.send_message(
            message.chat.id,
            'Использование команды: /log_water 250'
        )


@bot.message_handler(commands=['log_food'])
def log_food(message):
    logger.info(
        'Команда /log_food от пользователя %s: %s',
        message.chat.id,
        message.text
    )
    user = users.get(message.chat.id)
    if not user:
        bot.send_message(
            message.chat.id,
            'Сначала необходимо настроить профиль.'
        )
        return

    try:
        product_name = message.text.split(maxsplit=1)[1]
    except IndexError:
        bot.send_message(
            message.chat.id,
            'Использование команды: /log_food продукт'
        )
        return

    info = get_food_info(product_name)
    if not info:
        bot.send_message(message.chat.id, 'Продукт не найден.')
        return

    message_to_user = (
        f'{info["name"]}: {info["calories"]} ккал на 100 г.\n'
        'Введите количество грамм:'
    )

    msg = bot.send_message(message.chat.id, message_to_user)
    bot.register_next_step_handler(msg, save_food, info['calories'])


def save_food(message, calories_per_100g):
    try:
        grams = float(message.text)
        calories = grams / 100 * calories_per_100g
        users[message.chat.id]['logged_calories'] += calories

        bot.send_message(
            message.chat.id,
            f'Записано {int(calories)} ккал.'
        )
    except ValueError:
        bot.send_message(
            message.chat.id,
            'Ошибка ввода. Введите число.'
        )


@bot.message_handler(commands=['log_workout'])
def log_workout(message):
    logger.info(
        'Команда /log_workout от пользователя %s: %s',
        message.chat.id,
        message.text
    )
    user = users.get(message.chat.id)
    if not user:
        bot.send_message(
            message.chat.id,
            'Сначала необходимо настроить профиль.'
        )
        return

    try:
        _, workout_type, minutes = message.text.split()
        minutes = int(minutes)
    except ValueError:
        bot.send_message(
            message.chat.id,
            'Использование команды: /log_workout бег 30'
        )
        return

    calories = minutes * 10
    water_loss = (minutes // 30) * 200

    user['burned_calories'] += calories
    user['water_goal'] += water_loss

    bot.send_message(
        message.chat.id,
        f'Тренировка: {workout_type}, {minutes} минут.\n'
        f'Сожжено калорий: {calories}.\n'
        f'Дополнительная норма воды: {water_loss} мл.'
    )


@bot.message_handler(commands=['check_progress'])
def check_progress(message):
    logger.info('Команда /check_progress от пользователя %s', message.chat.id)
    user = users.get(message.chat.id)
    if not user:
        bot.send_message(
            message.chat.id,
            'Сначала необходимо настроить профиль.'
        )
        return

    bot.send_message(
        message.chat.id,
        'Текущий прогресс:\n\n'
        f'Вода:\n'
        f'- Выпито: {user["logged_water"]} мл\n'
        f'- Цель: {user["water_goal"]} мл\n\n'
        f'Калории:\n'
        f'- Потреблено: {int(user["logged_calories"])} ккал\n'
        f'- Сожжено: {user["burned_calories"]} ккал\n'
        f'- Цель: {user["calorie_goal"]} ккал'
    )


def main():
    if not check_tokens():
        sys.exit('Ошибка конфигурации.')

    logger.info('Бот запущен.')
    bot.infinity_polling()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    main()
