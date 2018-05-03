"""
Fill-in the information in config.json, and execute this file: python3.5 inlinetexbot.py.

The telepot library's (https://github.com/nickoala/telepot) Bot object is used to interface with the Telegram Bot API.
Inline queries are processed using an Answerer: this ensures that one client may have at most one process working on
their query. Old requests by the same user are abandoned: only the latest request is served.

InlineTeXBot creates a folder for each user it receives a query from, and uses this folder as an execution context
for the pdflatex command. This library is removed and re-created when a new query arrives, but no cleanup occurs when
the script terminates.
"""

import asyncio
import telepot
import telepot.aio
import telepot.aio.loop
from telepot.namedtuple import InlineQueryResultPhoto, InlineQueryResultArticle, InputTextMessageContent
from telepot.aio.loop import MessageLoop
from telepot.aio.helper import InlineUserHandler, AnswererMixin
from telepot.aio.delegate import per_inline_from_id, create_open, pave_event_space
import logging
import os
from aiohttp import web

from inlinetex_loggers import initialize_loggers
import config_reader
import latex_generator

class InlineHandler(InlineUserHandler, AnswererMixin):
    """
    async def handle(self, msg):
        flavor = telepot.flavor(msg)
        if flavor == 'normal':
            content_type, chat_type, chat_id = telepot.glance(msg, flavor)
            server_logger.info("Normal %s message, %s." % (content_type, chat_id))
            await bot.sendMessage(int(chat_id), "I'm an inline bot. You cannot speak to me directly")
        elif flavor == 'inline_query':
            msg_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
            server_logger.info("Inline equation, %s : %s" % (from_id, query_string))
            answerer.answer(msg)
    """
    def __init__(self, *args, **kwargs):
        super(InlineHandler, self).__init__(*args, **kwargs)
    async def on_inline_query(self, msg):
        async def compute_answer():
            query_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
            def get_error_query():
                return [InlineQueryResultArticle(id="latex_start", title='Invalid LaTex',
                                                 description="Couldn't parse your input.",
                                            input_message_content=InputTextMessageContent(     message_text="Sorry, I lost my way around. Didn't mean to send this."),
                                                 type='article')]
            if len(msg['query']) < 1: 
                results = [InlineQueryResultArticle(id="latex_start", title='Enter LaTeX',
                                                    description="Waiting to process your equation. No need to add math mode, "
                                                                    "I'll take care of that.",
                                                       input_message_content=InputTextMessageContent( message_text="Sorry, I lost my way around. Didn't mean to send this."),
                                                    thumb_url='http://a1.mzstatic.com/eu/r30/Purple69/v4/b2/f2/92/b2f292f4-a27f'
                                                              '-7ecc-fa20-19d84095e035/icon256.png', thumb_width=256,
                                                    thumb_height=256, type='article')]
            else:
                try:
                    jpg_url, width, height = await latex_generator.process(str(msg['from']['id']), msg['query'])
                except UnboundLocalError:   # probably failed to generate file
                    results = get_error_query()
                else:
                    results = [InlineQueryResultPhoto(id='Formatted equation', photo_url=jpg_url,
                                                      thumb_url=jpg_url, photo_height=height, photo_width=width)]
            return results
        #def compute_answer():
        #    query_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
        #    print(self.id, ':', 'Inline Query:', query_id, from_id, query_string)

        #    articles = [{'type': 'article',
        #                     'id': 'abc', 'title': query_string, 'message_text': query_string}]

        #    return articles
        #query_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
        #m_answer = await compute_answer(msg)
        self.answerer.answer(msg, compute_answer)


async def compute_answer():
    query_id, from_id, query_string = telepot.glance(msg, flavor='inline_query')
    def get_error_query():
        return [InlineQueryResultArticle(id="latex_start", title='Invalid LaTex',
                                         description="Couldn't parse your input.",
                                         message_text="Sorry, I lost my way around. Didn't mean to send this.",
                                         type='article')]
    if len(msg['query']) > 1: 
        print("Query > 1")
        results = [InlineQueryResultArticle(id="latex_start", title='Enter LaTeX',
                                            description="Waiting to process your equation. No need to add math mode, "
                                                            "I'll take care of that.",
                                                message_text="Sorry, I lost my way around. Didn't mean to send this.",
                                            thumb_url='http://a1.mzstatic.com/eu/r30/Purple69/v4/b2/f2/92/b2f292f4-a27f'
                                                      '-7ecc-fa20-19d84095e035/icon256.png', thumb_width=256,
                                            thumb_height=256, type='article')]
    else:
        try:
            print("Test")
            jpg_url, width, height = await latex_generator.process(str(msg['from']['id']), msg['query'])
        except UnboundLocalError:   # probably failed to generate file
            results = get_error_query()
        else:
            results = [InlineQueryResultPhoto(id='Formatted equation', photo_url=jpg_url,
                                              thumb_url=jpg_url, photo_height=height, photo_width=width)]
    return results

initialize_loggers()

TOKEN = config_reader.token

bot = telepot.aio.DelegatorBot(TOKEN, [
    pave_event_space()(
        per_inline_from_id(), create_open, InlineHandler, timeout=10),
])

server_logger = logging.getLogger('server_logger')

loop = asyncio.get_event_loop()
latex_generator.loop = loop
latex_generator.run_dir = os.getcwd()
loop.create_task(MessageLoop(bot).run_forever())

# python 3
from http.server import HTTPServer as BaseHTTPServer, SimpleHTTPRequestHandler

class HTTPHandler(SimpleHTTPRequestHandler):
    """This handler uses server.base_path instead of always using os.getcwd()"""
    def translate_path(self, path):
        path = SimpleHTTPRequestHandler.translate_path(self, path)
        relpath = os.path.relpath(path, os.getcwd())
        fullpath = os.path.join(self.server.base_path, relpath)
        return fullpath


class HTTPServer(BaseHTTPServer):
    """The main server, you pass in base_path which is the path you want to serve requests from"""
    def __init__(self, base_path, server_address, RequestHandlerClass=HTTPHandler):
        self.base_path = base_path
        BaseHTTPServer.__init__(self, server_address, RequestHandlerClass)

print("Listening...")
async def handle(request):
    name = request.match_info.get('name', "Anonymous")
    text = "Hello, " + name
    return web.Response(text=text)

app = web.Application()
print(os.path.join(os.getcwd(), 'img'))
app.router.add_static('/', os.path.join(os.getcwd(), 'img'))

web.run_app(app)
loop.run_forever()
