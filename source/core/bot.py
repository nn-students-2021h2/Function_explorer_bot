"""
Main core module with bot and logger functionality
"""
import asyncio
import logging
import subprocess
import time
from enum import Enum
from functools import total_ordering
from subprocess import run, STDOUT, PIPE

import pymongo.collection
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.exceptions import TelegramAPIError
from pymongo import MongoClient, errors

import handling_msg as hmsg
from source.conf.config import Config
from source.conf.custom_logger import setup_logging
from source.math.graph import Graph

# Enable logging
logger = logging.getLogger(__name__)
setup_logging(logger)

# Set up a bot
token = Config().properties["APP"]["TOKEN"]
bot: Bot = Bot(token=token)
dispatcher: Dispatcher = Dispatcher(bot, storage=MemoryStorage())


@total_ordering
class Status(Enum):
    """Enum for define statuses of chat"""
    MAIN = 0
    GRAPH = 1
    ANALYSE = 2
    DERIVATIVE = 3
    DOMAIN = 4
    RANGE = 5
    ZEROS = 6
    AXES_INTERSECTION = 7
    PERIODICITY = 8
    CONVEXITY = 9
    CONCAVITY = 10
    CONTINUITY = 11
    V_ASYMPTOTES = 12
    H_ASYMPTOTES = 13
    S_ASYMPTOTES = 14
    ASYMPTOTES = 15
    EVENNESS = 16
    ODDNESS = 17
    MAXIMUM = 18
    MINIMUM = 19
    STATIONARY_POINTS = 20
    ANALYSE_MENU = 21

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented


hostname = "google.com"

cmd = f"ping {hostname}"

last_ping = ""  # Cache of pint. It sent to user if minute is not left.
waiting_time = 60  # One minute timeout
last_ping_time = waiting_time  # Last time when hostname was pinged

no_db_message = "There were problems, the functionality is limited.\nYou can only use the bot with commands."

chat_status_table: pymongo.collection.Collection
"""Collection that returns the Status of user by chat id"""


def init_pymongo_db():
    """Initialise connection to mongo database"""
    global chat_status_table
    conf = Config()
    client = MongoClient(conf.properties["DB_PARAMS"]["ip"], conf.properties["DB_PARAMS"]["port"],
                         serverSelectionTimeoutMS=5000)
    try:
        logger.debug(client.server_info())
    except errors.PyMongoError:
        logger.critical("Unable to connect to the MongoDB server.")
    db = client[conf.properties["DB_PARAMS"]["database_name"]]
    chat_status_table = db["chat_status"]
    chat_status_table.create_index("chat_id", unique=True)


async def anti_flood(*args, **kwargs):
    """This function is called when user's message has been throttled"""
    await args[0].answer(f"Flood is not allowed! You should wait {kwargs['rate']} seconds to repeat this action.")


async def change_user_status(message: types.Message, status: Status) -> int:
    """Update user status in mongo database. It returns 1 if the connection is lost and 0 if all ok"""
    try:
        if chat_status_table.find_one({"chat_id": message.chat.id}) is None:
            chat_status_table.insert_one({"chat_id": message.chat.id, "status": status.value})
        else:
            chat_status_table.update_one({"chat_id": message.chat.id}, {"$set": {"status": status.value}})
        return 0
    except errors.PyMongoError:
        await bot.send_message(message.chat.id, no_db_message)
        return 1


async def go_main(message: types.Message):
    """Change status of user and send main menu to user."""
    if await change_user_status(message, Status.MAIN):
        return
    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True).add("Draw graph", "Analyse function",
                                                                 "Get help", f"Ping {hostname}")
    await bot.send_message(message.chat.id, 'Choose action', reply_markup=reply_markup)


async def go_graph(message: types.Message):
    """Change status of user and send draw graph menu to user."""
    if await change_user_status(message, Status.GRAPH):
        return
    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True).add("Main menu")
    await bot.send_message(message.chat.id, "Enter function to draw or go to main menu", reply_markup=reply_markup)


async def go_analyse(message: types.Message):
    """Change status of user to 'analyse' and send analyse menu"""
    if await change_user_status(message, Status.ANALYSE):
        return
    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True).add("Options", "Get help", "Main menu")
    await bot.send_message(message.chat.id, "Choose option or enter command or go to main menu",
                           reply_markup=reply_markup)


async def go_analyse_menu(message: types.Message):
    """Change status of user to 'analyze menu' and send options to analyze menu'"""
    if await change_user_status(message, Status.ANALYSE_MENU):
        return
    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True).add('Derivative', 'Domain', 'Range',
                                                                 'Stationary points', 'Periodicity',
                                                                 'Continuity', 'Convexity', 'Concavity',
                                                                 'Horizontal asymptotes', 'Vertical asymptotes',
                                                                 'Asymptotes', 'Evenness', 'Oddness',
                                                                 'Axes intersection', 'Slant asymptotes',
                                                                 'Maximum', 'Minimum', 'Zeros',
                                                                 'Main menu', 'Back')
    await bot.send_message(message.chat.id, "Choose option to analyze or go back", reply_markup=reply_markup)


async def go_analyse_option(message: types.Message, option: Status):
    """Change status of user to option and send 'go back' menu'"""
    if await change_user_status(message, option):
        return
    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True).add("Back", "Main menu")
    await bot.send_message(message.chat.id, "Enter function to analyse or go back", reply_markup=reply_markup)


status_dict = {
    'Derivative': Status.DERIVATIVE,
    'Domain': Status.DOMAIN,
    'Range': Status.RANGE,
    'Zeros': Status.ZEROS,
    'Axes intersection': Status.AXES_INTERSECTION,
    'Periodicity': Status.PERIODICITY,
    'Convexity': Status.CONVEXITY,
    'Concavity': Status.CONCAVITY,
    'Continuity': Status.CONTINUITY,
    'Vertical asymptotes': Status.V_ASYMPTOTES,
    'Horizontal asymptotes': Status.H_ASYMPTOTES,
    'Slant asymptotes': Status.S_ASYMPTOTES,
    'Asymptotes': Status.ASYMPTOTES,
    'Evenness': Status.EVENNESS,
    'Oddness': Status.ODDNESS,
    'Maximum': Status.MAXIMUM,
    'Minimum': Status.MINIMUM,
    'Stationary points': Status.STATIONARY_POINTS
}
"""A dictionary that returns Status by string and string by Status"""
# Adding Status: string matching to status_dict
status_dict.update({value: key.lower() for key, value in status_dict.items()})


@dispatcher.message_handler(commands=["start"])
@dispatcher.throttled(anti_flood, rate=0.5)
async def start(message: types.Message):
    """Send a message when the command /start is issued."""
    await bot.send_message(message.chat.id, f'Hello, {message.from_user.first_name} {message.from_user.last_name}!')
    await go_main(message)


@dispatcher.message_handler(commands=["help"])
@dispatcher.throttled(anti_flood, rate=0.5)
async def chat_help(message: types.Message):
    """Send a message when the command /help is issued."""
    await bot.send_message(message.chat.id, 'Enter:\n/start to restart bot.\n/graph to draw graph.\n/analyse to '
                                            'go on to investigate the function.')


@dispatcher.message_handler(commands=["graph"])
@dispatcher.throttled(anti_flood, rate=2)
async def graph(message: types.Message):
    """Draw graph, save it as image and send to the user."""
    if message.text == '/graph':
        await go_graph(message)
    else:
        # await hmsg.send_graph(message)
        asyncio.create_task(hmsg.send_graph(message, ))


@dispatcher.message_handler(commands=["analyse"])
@dispatcher.throttled(anti_flood, rate=2)
async def analyse(message: types.Message):
    """Calculate requested function and send result to the user in LaTeX format (or not LaTeX - check config file)"""
    if message.text == '/analyse':
        await go_analyse(message)
    else:
        await hmsg.send_analyse(message)


@dispatcher.message_handler(commands=["meme"])
@dispatcher.throttled(anti_flood, rate=2)
async def meme(message: types.Message):
    """Call meme-api and send random meme from Reddit to user"""
    await hmsg.send_meme(message)


async def ping_google(message: types.Message):
    """Homework. Ping google.com and send min, max and avg time to user."""
    global last_ping
    output = ""
    await asyncio.sleep(2)
    try:
        output = run(cmd.split(), stdout=PIPE, stderr=STDOUT, text=True, encoding='cp866',
                     check=True).stdout.split('\n')
    except subprocess.CalledProcessError:
        logger.error("Subprocess.run returns non-zero code")
    last_ping = ("Approximate round-trip time in ms:\n" +
                 output[-2].replace('мсек', 'ms').replace('Минимальное', 'Min')
                 .replace('Максимальное', 'Max')
                 .replace('Среднее', 'Avg'))
    await message.reply(last_ping)


@dispatcher.message_handler(content_types=["text"])
@dispatcher.throttled(anti_flood, rate=0.5)
async def default_handler(message: types.Message):
    """Checks user status and direct his message to suitable function."""
    global last_ping_time
    try:
        chat_status = Status(chat_status_table.find_one({"chat_id": message.chat.id})['status'])
    except errors.PyMongoError:
        await bot.send_message(message.chat.id, no_db_message)
        return
    if message.text == f'Ping {hostname}':
        if last_ping != "" and time.time() - last_ping_time < waiting_time:
            await message.reply(last_ping)
        else:
            last_ping_time = time.time()
            asyncio.create_task(ping_google(message, ))
        return
    if chat_status == Status.MAIN:
        match message.text:
            case 'Draw graph':
                await go_graph(message)
            case 'Analyse function':
                await go_analyse(message)
            case 'Get help':
                await chat_help(message)
            case _:
                await message.reply(hmsg.echo())
    elif chat_status == Status.ANALYSE:
        match message.text:
            case 'Main menu':
                await go_main(message)
            case 'Options':
                await go_analyse_menu(message)
            case 'Get help':
                await bot.send_message(message.chat.id, 'No')
            case _:
                await message.reply(hmsg.echo())
    elif chat_status == Status.ANALYSE_MENU:
        match message.text:
            case 'Back':
                await go_analyse(message)
            case 'Main menu':
                await go_main(message)
            case _:
                await go_analyse_option(message, status_dict[message.text])
    elif Status.DERIVATIVE <= chat_status <= Status.STATIONARY_POINTS:
        match message.text:
            case 'Back':
                await go_analyse_menu(message)
            case 'Main menu':
                await go_main(message)
            case _:
                message.text = f'{status_dict[chat_status]} {message.text.lower()}'
                await hmsg.send_analyse(message)
                await bot.send_message(message.chat.id, "Enter function to explore or go back")
    elif chat_status == Status.GRAPH:
        match message.text:
            case 'Main menu':
                await go_main(message)
            case _:
                await hmsg.send_graph(message)
                await bot.send_message(message.chat.id, "Enter function to draw or go main menu")


@dispatcher.errors_handler()
def error(update: types.Update, exception: TelegramAPIError):
    """Log Errors caused by Updates."""
    logger.error('Update %s\nCaused error %s', update, exception)


if __name__ == '__main__':
    init_pymongo_db()
    Graph.setup_plot_style()
    logger.info('Bot is started')
    dispatcher.middleware.setup(LoggingMiddleware(logger=logger))
    executor.start_polling(dispatcher)
