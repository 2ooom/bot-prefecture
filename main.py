#!/usr/bin/env python3

import logging
import sys
import os
import concurrent.futures
import threading

from browser import Browser
from telegram_bot import TelegramBot
from http_client import HttpClient
from watcher import Watcher
from users_data import form_data, anticaptcha_api_key, telegram_bot_token, proxy_config
from config import config
from utils import setup_logging, DUMPS_FOLDER
from metrics import Metrics

DB_PATH = './bot_state.json'
LOG_PATH = './execution.log'
PROXIES_PATH = './proxies.txt'

def get_watcher():
    tg_bot = TelegramBot(telegram_bot_token, DB_PATH)
    http_client = HttpClient(PROXIES_PATH)
    browsers = []

    for data in form_data:
        br = Browser(config, data, tg_bot, http_client)
        browsers.append(br)
    metrics = Metrics(export_metrics=False)
    return Watcher(tg_bot, http_client, browsers[0].url_start, browsers, metrics, use_say_cmd=True)

if __name__ == "__main__":
    setup_logging(LOG_PATH)
    logger = logging.getLogger("Global")

    if not os.path.exists(DUMPS_FOLDER):
        os.makedirs(DUMPS_FOLDER)

    watcher = get_watcher()
    watcher.start_loop(
        max_attempts=int(sys.argv[1]) if len(sys.argv) > 1 else None,
        parallelism=1
    )
    logger.info(f"Waiting for {len(watcher.form_submit_threads)} submit actions to finish")
    for th in watcher.form_submit_threads:
        th.join()

    logger.info("Done. Exiting")