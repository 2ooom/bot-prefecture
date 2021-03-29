import logging
import sys
import os
import threading

from watcher import Watcher
from browser import Browser
from telegram_bot import TelegramBot
from http_client import HttpClient
from users_data import form_data, anticaptcha_api_key, telegram_bot_token, proxy_config, azure_insights

from config import config

from flask import Flask, escape, request
from main import DB_PATH, LOG_PATH, PROXIES_PATH
from utils import DUMPS_FOLDER
from datetime import datetime as dt
from metrics import Metrics

from opencensus.ext.azure.log_exporter import AzureLogHandler

def setup_logging(filepath):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)-5.5s] [%(name)s] %(message)s', "%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)
    root_logger.addHandler(ch)

    az = AzureLogHandler(connection_string=azure_insights.connection_string)
    az.setLevel(logging.INFO)
    root_logger.addHandler(az)


setup_logging(LOG_PATH)

app = Flask(__name__)

logger = logging.getLogger("Server")

if not os.path.exists(DUMPS_FOLDER):
    os.makedirs(DUMPS_FOLDER)

service_started = dt.now()
tg_bot = TelegramBot(telegram_bot_token, DB_PATH)
http_client = HttpClient(PROXIES_PATH)
browsers = []

for data in form_data:
    br = Browser(config, data, tg_bot, http_client, wait_for_input=False)
    br.preload()
    browsers.append(br)

metrics = Metrics(export_metrics=True)
watcher = Watcher(tg_bot, http_client, browsers[0].url_start, browsers, metrics, use_say_cmd=False)
watcher_thread = threading.Thread(target=watcher.start_loop, args=(None, 1), daemon=True)
watcher_thread.start()
logger.info("Started watching for dates")


@app.route('/')
def index():
    avg_req_time = watcher.global_time_counter/watcher.global_req_counter if watcher.global_req_counter else 0
    metrics = [
        f"Nb. requests: {watcher.global_req_counter}",
        f"Average request time: {'{:.2f}'.format(avg_req_time)} s",
        f"Service uptime: {(dt.now() - service_started)}"
    ]
    return "<br/>".join(metrics)
