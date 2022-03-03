"""
In this module we process events related to bot (such as messages, requests)
"""
from asyncio import sleep
from io import BytesIO

import aiogram.utils.exceptions
import requests
import sympy as sy
import telegram
from PIL import Image, ImageOps
from aiogram import types

from source.conf import Config
from source.core.bot import logger, bot
from source.math.calculus_parser import CalculusParser
from source.math.graph import Graph, DrawError
from source.math.graph_parser import GraphParser, ParseError

# We get "USE_LATEX" parameter from settings
SETTINGS = Config()

# A number of dots per inch for TeX pictures
DPI = '600'


def resize_image(image_to_resize: BytesIO, output_buffer: BytesIO):
    """
    Resize image to fit in the Telegram window and add a frame
    :param image_to_resize: a BytesIO object containing the image you want to resize
    :param output_buffer: result image buffer
    """
    image_to_resize.seek(0)
    output_buffer.seek(0)

    image = Image.open(BytesIO(image_to_resize.read()))
    height, width = image.size
    max_size = 10000

    # Resize to max size
    if height > max_size or width > max_size:
        ratio = min(max_size / height, max_size / width)
        image.thumbnail((int(height * ratio), int(width * ratio)))

    # Set borders
    # noinspection PyTypeChecker
    ImageOps.expand(image, border=100, fill="white").save(output_buffer, format="PNG")
    output_buffer.seek(0)


def echo():
    """On simple messages bot replies that didn't understand user"""
    return 'I didn\'t understand what you want'


async def send_graph(message: types.Message):
    """User requested to draw a plot"""
    chat_id = message.chat.id
    if message.get_command():
        expr = message.get_args().lower()
    else:
        expr = message.text.lower()

    logger.info("User [chat_id=%s] requested to draw a graph. User's input: `%s`", chat_id, expr)

    parser = GraphParser()

    try:
        parser.parse(expr)
        graph = Graph()
        image = graph.draw(parser.tokens)
    except ParseError as err:
        await message.reply(str(err))
        logger.info("ParseError exception raised on user's [chat_id=%s] input: `%s`", chat_id, expr)
        return
    except DrawError as err:
        await message.reply(str(err))
        logger.info("DrawError exception raised on user's [chat_id=%s] input: `%s`", chat_id, expr)
        return

    output_message = "Here a graph of requested functions"
    await sleep(0.1)
    await bot.send_photo(
        chat_id=chat_id,
        photo=image,
        caption=output_message + '\n' + "\n".join(parser.warnings)
    )
    image.close()

    parser.clear_warnings()


async def send_analyse(message: types.Message):
    """User requested some function analysis"""
    chat_id = message.chat.id
    if message.get_command():
        expr = message.get_args().lower()
    else:
        expr = message.text.lower()

    logger.info("User [chat_id=%s] requested an analysis. User's input: `%s`", chat_id, expr)

    parser = CalculusParser()

    try:
        # Parse the request and check if any pattern was found
        # If parser can't understand what the user means, it returns False
        is_pattern_found = parser.parse(expr)
        if not is_pattern_found:
            await message.reply("Couldn't find a suitable template. Check the input.")
            logger.info("Bot doesn't find any pattern for user's [id=%s] input: `%s`", chat_id, expr)
            return

        result = parser.process_query()

        # If USE_LATEX set in True, then send picture to the user. Else, send basic text
        if SETTINGS.properties["APP"]["USE_LATEX"]:
            latex = parser.make_latex(result)
            with BytesIO() as latex_picture, BytesIO() as resized_image:
                sy.preview(fr'${latex}$', output='png', viewer='BytesIO', outputbuffer=latex_picture,
                           dvioptions=['-D', DPI])

                resize_image(latex_picture, resized_image)

                # If we can't send photo due to Telegram limitations, then send image as file instead
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=resized_image,
                        caption="\n".join(parser.warnings)
                    )
                except telegram.error.BadRequest:
                    parser.push_warning("Photo size is too large, therefore I send you a file.")
                    await bot.send_document(
                        chat_id=chat_id,
                        document=resized_image,
                        caption="\n".join(parser.warnings)
                    )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=str(result)
            )
        parser.clear_warnings()
    except ParseError as err:
        await message.reply(str(err))
        logger.info("ParseError exception raised on user's [chat_id=%s] input: `%s`", chat_id, expr)
    except RecursionError:
        await message.reply("Incorrect input. Please check your function.")
        logger.warning("RecursionError exception raised on user's [chat_id=%s] input: `%s`", chat_id, expr)
    except (ValueError, NotImplementedError):
        await message.reply("Sorry, a feature isn't implemented or input is invalid. Please check your function.")
        logger.warning("ValueError or NotImplementedError exception raised on user's [chat_id=%s] input: `%s`", chat_id,
                       expr)


async def send_meme(message: types.Message):
    """User requested some meme"""
    chat_id = message.chat.id
    logger.info("User [id=%s] requested a meme", chat_id)

    response = requests.get("https://meme-api.herokuapp.com/gimme/").json()
    url = response["url"]
    post_link = response["postLink"]
    headers = requests.head(url).headers

    try:
        if headers["Content-Type"] == "image/gif":
            await bot.send_animation(
                chat_id=chat_id,
                animation=url,
                caption=post_link
            )
        else:
            await bot.send_photo(
                chat_id=chat_id,
                photo=url,
                caption=post_link
            )
    except aiogram.utils.exceptions.BadRequest as err:
        logger.warning("User [id=%s] catches a BadRequest getting a meme: %s", chat_id, err)
        await bot.send_message(
            chat_id=chat_id,
            text="Sorry, something went wrong. Please try again later."
        )
