#!/usr/bin/env python3

import logging
import os
import threading
import argparse

from browser import Browser
from telegram_bot import TelegramBot
from http_client import HttpClient
from watcher import Watcher
from watcher_multislot import WatcherMultislot
from users_data import form_data
from config import configs
from utils import DUMPS_FOLDER, WEBSITE_HOSTNAME, now
from metrics import Metrics
from credentials_store import CredentialsStore
from mail_checker import MailChecker

LOG_PATH = './execution.log'

def setup_logging(filepath):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)-5.5s] [%(name)s] %(message)s', "%H:%M:%S")

    fh = logging.FileHandler(filepath, mode='a')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    root_logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)
    root_logger.addHandler(ch)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Utilities for booking RDV in 🇫🇷 prefectures')
    parser.add_argument('--nb-attempts', '-n', type=int, help='Number of attempts for chosen action(s)')
    parser.add_argument('--watch', default='website,email', help='What should be watched: `website` - checks dates on the prefecture website. `email` - checks gmail inbox for confirmation email')
    parser.add_argument('--config', default='hauts-de-seine-bio', help='Name of prefecture to watch dates for')
    parser.add_argument('--parallelism', default=1, type=int, help='Number of parallel threads checking for the same week')

    args = parser.parse_args()
    watch_types = set(args.watch.split(','))
    setup_logging(LOG_PATH)

    logger = logging.getLogger("Global")
    tg_bot = TelegramBot()
    config = configs[args.config]
    logger.info(f'Using config for {args.config} prefecture')

    if not os.path.exists(DUMPS_FOLDER):
        os.makedirs(DUMPS_FOLDER)

    if not os.environ.get(WEBSITE_HOSTNAME):
        os.environ[WEBSITE_HOSTNAME] = f'localhost-main-{now()}'

    if 'email' in watch_types:
        store = CredentialsStore()

        def start_mail_checker_thread(email):
            mail_checker = MailChecker(store, email, config, tg_bot)
            return mail_checker.start_loop(args.nb_attempts)

        mail_checkers = list(map(lambda data: start_mail_checker_thread(data['email']), form_data))
        logger.info(f"Waiting for {len(mail_checkers)} email checking threads to finish")
        for th in mail_checkers:
            th.join()

    if 'website' in watch_types:
        http_client = HttpClient()
        #browsers = list(map(lambda data: Browser(config, data, tg_bot, http_client), form_data))
        metrics = Metrics(export_metrics=False)
        watcher = WatcherMultislot(tg_bot, http_client, metrics, config, args.parallelism)
        watcher.start_loop(
            max_attempts=args.nb_attempts
        )
        logger.info(f"Waiting for {len(watcher.form_submit_threads)} submit actions to finish")
        for th in watcher.form_submit_threads:
            th.join()

    logger.info("Done. Exiting")