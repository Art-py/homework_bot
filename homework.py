import os
import sys
import time
import logging
from http import HTTPStatus

import telegram
import requests
from dotenv import load_dotenv
from exceptions import BadReturnAnswer, EmptyDict, WrongDataType, CheckingKeys

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
    """Отправляет сообщение в чат телеграмма"""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info(f'Бот отправил сообщение {message}')
    except Exception as error:
        logger.error(f'Не удалось отправить сообщение в телеграмм: {error}')


def get_api_answer(current_timestamp: int) -> dict:
    """Получает ответ от сервера и возвращает результат."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except Exception as error:
        logger.error(f'Сбой в работе программы: '
                      f'Эндпоинт {ENDPOINT} недоступен. '
                      f'Код ответа: {homework_statuses.status_code}')
    if homework_statuses.status_code != HTTPStatus.OK:
        logger.error('Некоректный ответ от сервера.')
        raise BadReturnAnswer('Некоректный ответ от сервера.')
    return homework_statuses.json()


def check_response(response: dict) -> dict:
    if response:
        if 'homeworks' not in response:
            logger.error('Отсутствует ключ homeworks, в ответе API')
            raise CheckingKeys('Отсутствует ключ homeworks, в ответе API')
        elif 'current_date' not in response:
            logger.error('Отсутствует ключ current_date, в ответе API')
            raise CheckingKeys('Отсутствует ключ current_date, в ответе API')
        else:
            return {'result': True, 'answer': response.get('homeworks')}
    else:
        logger.info('Ответ пришел пустым!')
        raise EmptyDict('Ответ пришел пустым!')
    # Если словарь пришел пустым значит проверять нечего, завершаем работу.
    return {'result': False, 'answer': {}}


def parse_status(homework: dict) -> str:
    """
    извлекает из информации о конкретной домашней работе статус этой работы.
    """
    if isinstance(homework, str):
        logger.error('В функцию parse_status, пришла строка вместо словаря!')
        raise WrongDataType(
            'В функцию parse_status, пришла строка вместо словаря!'
        )
    else:
        homework_name = homework.get('homework_name')
        homework_status = homework.get('status')
        verdict = HOMEWORK_STATUSES.get(homework_status)
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'

def check_tokens() -> bool:
    """Проверяет переменные окружения, при отсутствии, работа прекращается."""
    if PRACTICUM_TOKEN is None:
        logger.critical(f'Отсутствует обязательная переменная окружения:'
                         f'PRACTICUM_TOKEN'
                         f'Программа принудительно остановлена.')
        return False
    if TELEGRAM_TOKEN is None:
        logger.critical(f'Отсутствует обязательная переменная окружения:'
                         f'TELEGRAM_TOKEN'
                         f'Программа принудительно остановлена.')
        return False
    if TELEGRAM_CHAT_ID is None:
        logger.critical(f'Отсутствует обязательная переменная окружения:'
                         f'TELEGRAM_CHAT_ID'
                         f'Программа принудительно остановлена.')
        return False
    return True


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - 60 * 60 * 24 * 31
    status_homework_glob = ''

    while True:
        try:
            if not check_tokens():
                return
            response = get_api_answer(current_timestamp)
            response = check_response(response)
            if not response.get('result'):
                return
            if status_homework_glob != response.get('answer'):
                status_homework_glob = response.get('answer')
                message_status = parse_status(
                    response.get('answer')[LAST_ELEMENT]
                )
                send_message(bot, message_status)
            # current_timestamp = ...
            time.sleep(RETRY_TIME)
            logger.info('Цикл прошел отлично!')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            time.sleep(RETRY_TIME)
        else:
            pass


if __name__ == '__main__':
    main()
