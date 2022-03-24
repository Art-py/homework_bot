import os
import sys
import time
import logging
from http import HTTPStatus

import telegram
import requests
from dotenv import load_dotenv
from typing import Union

from exceptions import BadReturnAnswer

try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# Добавляем файловый лог
fileHandler = logging.FileHandler('homework.log')
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)
# Добавляем вывод лога в консоль
streamHandler = logging.StreamHandler(sys.stdout)
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
LAST_ELEMENT = -1


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot: telegram.bot, message: str):
    """Отправляет сообщение в чат телеграмма."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Бот отправил сообщение {message}')
    except telegram.error.TelegramError as error:
        logger.error(f'Не удалось отправить сообщение в телеграмм: {error}')


def get_api_answer(current_timestamp: int) -> Union[dict, str]:
    """Получает ответ от сервера и возвращает результат."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    answer_str = 'Сбой в работе эндпойнта'
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except requests.exceptions.HTTPError as error:
        logger.error(f'Сбой в работе программы: '
                     f'Эндпоинт {ENDPOINT} недоступен. '
                     f'Код ответа: {homework_statuses.status_code}.'
                     f'Ошибка: {error}')
        return answer_str
    except requests.exceptions.Timeout as error:
        logger.error(f'Сбой в работе программы! Ошибка url: {error}')
        return answer_str
    except requests.exceptions.ConnectionError as error:
        logger.error(f'Ошибка соединения: {error}')
        return answer_str
    except requests.exceptions.RequestException as error:
        logger.error(f'Что то пошло не так: {error}')
        return answer_str

    if homework_statuses.status_code != HTTPStatus.OK:
        logger.error('Некоректный ответ от сервера.')
        raise BadReturnAnswer('Некоректный ответ от сервера.')
    try:
        ret_answer = homework_statuses.json()
        return ret_answer
    except JSONDecodeError:
        logger.error('Не удалось получить ответ от сервера!')


def check_response(response: dict) -> dict:
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        logger.error('Пришел неверный тип данных от сервера!')
        raise TypeError('Пришел неверный тип данных от сервера!')

    if 'homeworks' not in response:
        logger.error('Отсутствует ключ homeworks, в ответе API')
        raise KeyError('Отсутствует ключ homeworks, в ответе API')
    elif 'current_date' not in response:
        logger.error('Отсутствует ключ current_date, в ответе API')
        raise KeyError('Отсутствует ключ current_date, в ответе API')
    else:
        answer = response.get('homeworks')
        if not isinstance(answer, list):
            logger.error('Пришел неверный тип данных от сервера!')
            raise TypeError('Пришел неверный тип данных от сервера!')
        return answer


def return_check_status(homework):
    """Проверяет и возвращает статус домашнего задания."""
    if 'status' not in homework:
        logger.error('Отсутствует ключ status, в ответе API')
        raise KeyError('Отсутствует ключ status, в ответе API')
    else:
        homework_status = homework.get('status')
        if homework_status not in HOMEWORK_STATUSES:
            logger.error(f'Недокументированный статус {homework_status}')
            raise KeyError(
                f'Недокументированный статус {homework_status}'
            )
        return homework_status


def parse_status(homework: dict) -> str:
    """Извлекает из информации о домашней работе, статус этой работы."""
    if not isinstance(homework, dict):
        logger.error('Пришел неверный тип данных от сервера!')
        raise TypeError('Пришел неверный тип данных от сервера!')

    homework_status = return_check_status(homework)

    if 'homework_name' not in homework:
        logger.error('Отсутствует ключ homework_name, в ответе API')
        raise KeyError('Отсутствует ключ homework_name, в ответе API')
    else:
        homework_name = homework.get('homework_name')

    verdict = HOMEWORK_STATUSES.get(homework_status)
    return (f'Изменился статус проверки работы '
            f'"{homework_name}". {verdict}')


def check_tokens() -> bool:
    """Проверяет переменные окружения, при отсутствии, работа прекращается."""
    if PRACTICUM_TOKEN is None:
        logger.critical('Отсутствует обязательная переменная окружения:'
                        'PRACTICUM_TOKEN '
                        'Программа принудительно остановлена.')
        return False
    if TELEGRAM_TOKEN is None:
        logger.critical('Отсутствует обязательная переменная окружения: '
                        'TELEGRAM_TOKEN '
                        'Программа принудительно остановлена.')
        return False
    if TELEGRAM_CHAT_ID is None:
        logger.critical('Отсутствует обязательная переменная окружения: '
                        'TELEGRAM_CHAT_ID '
                        'Программа принудительно остановлена.')
        return False
    return True


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - 60 * 60 * 24
    response_status_glob = ''

    while True:
        try:
            if not check_tokens():
                time.sleep(RETRY_TIME)
                continue
            response = get_api_answer(current_timestamp)
            if isinstance(response, str):
                time.sleep(RETRY_TIME)
                continue
            response = check_response(response)
            if not response:
                logger.info('Пришел пустой ответ от сервера!')
                time.sleep(RETRY_TIME)
                continue
            homework_status = return_check_status(response[LAST_ELEMENT])
            if response_status_glob != homework_status:
                response_status_glob = homework_status
                message_status = parse_status(response[LAST_ELEMENT])
                send_message(bot, message_status)
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
