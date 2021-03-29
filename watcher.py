
import logging
import time
import os
import sys
import subprocess
import requests
import threading
import random

from requests.exceptions import ReadTimeout, ProxyError
from browser import Browser
from telegram_bot import TelegramBot
from http_client import HttpClient
from users_data import form_data, anticaptcha_api_key, telegram_bot_token, proxy_config
from config import config
from utils import save_html

from datetime import datetime as dt
from lxml import html
from collections import defaultdict

class Watcher:
    DELAY_IF_NOT_FOUND_SEC = 1
    NOTIFICATIONS_DELAY = 7

    def __init__(self, tg_bot, http_client, start_url, browsers, metrics, use_say_cmd=True):
        self.logger = logging.getLogger(Watcher.__name__)
        self.start_url = start_url
        self.http_client = http_client
        self.tg_bot = tg_bot
        self.browsers = browsers
        self.metrics = metrics

        self.last_send_message = None
        self.global_req_counter = 0
        self.global_time_counter = 0
        self.form_submit_threads = []
        self.week_futures = []
        self.use_say_cmd = True

    def check_once(self, week, week_logger):
        date_table = self.http_client.get(
            f"{config.url}/ezjscore/call/bookingserver::planning::assign::{config.form_id}::{config.ajax_id}::{week}"
        )
        if not date_table:
            return
        tree = html.fromstring(date_table.content)
        date_links = tree.xpath(f".//a[contains(@href, 'booking/create/{config.form_id}/5')]")
        dates_period = tree.xpath(".//th[@colspan='7']")[0].text.strip()
        if not date_links:
            week_logger.debug(f'No dates found. {dates_period}')
            time.sleep(Watcher.DELAY_IF_NOT_FOUND_SEC)
            return
        date_urls = list(map(lambda l: l.attrib["href"], date_links))
        date_urls.sort()
        timestamps = list(map(lambda url: int(url.split("/")[-1]), date_urls))
        dates = list(map(lambda ts: dt.fromtimestamp(ts), timestamps))
        week_logger.warning('Dates found:')
        time_by_date = defaultdict(list)
        for d in dates:
            date_str = d.strftime("%d %b")
            time_str = d.strftime("%H:%M;")
            time_by_date[date_str].append(time_str)

        times_str = []
        for day, times in time_by_date.items():
            all_times = " ".join(times)
            times_str.append(f'🗓 *{day}*\n {all_times}\n')
            week_logger.warning(f'{day}: {all_times}')
        seconds_passed = self.get_seconds_since_notification()
        if not seconds_passed or seconds_passed >= Watcher.NOTIFICATIONS_DELAY:
            dates_list = "\n".join(times_str)
            self.tg_bot.send_all("\n".join([
                f'⚡️⚡️⚡️ {len(dates)} date(s) found ⚡️⚡️⚡️ :',
                f'*{dates_period}*',
                '',
                dates_list,
                '',
                '*Book RDV now by clicking*:'
                f'[{self.start_url}]({self.start_url})'
            ]))
            if self.use_say_cmd:
                subprocess.Popen(['say', '"Dates Available."'])

            self.last_send_message = dt.now()
        else:
            week_logger.info(f'Not sending notification {seconds_passed} seconds elapsed since previous')

        middle_index = int(len(date_urls) / 2)
        date_url = date_urls[middle_index]
        week_logger.warning(f'Chosen first date: {dates[middle_index].isoformat()} (unix timestamp: {timestamps[middle_index]})')
        browsers_without_rdv = list(filter(lambda b: not b.rdv_taken, self.browsers))
        if not browsers_without_rdv:
            self.logger.warning(f"All programmed RDVs taken (total {len(self.browsers)}). Skipping both submits")
            return
        submit_thread = threading.Thread(target=browsers_without_rdv[0].submit_form, args=(date_url, dates[middle_index], timestamps[middle_index]))
        self.form_submit_threads.append(submit_thread)
        submit_thread.start()
        if len(browsers_without_rdv) == 1:
            self.logger.warning(f"Only single RDVs needed (total {len(self.browsers)}). Skipping second submit")
            return
        if len(date_urls) > 1:
            another_date_url = None
            second_index = -1
            if middle_index + 1 < len(date_urls) and dates[middle_index + 1].date() == dates[middle_index].date():
                second_index = middle_index + 1
            elif middle_index > 0 and dates[middle_index - 1].date() == dates[middle_index].date():
                second_index = middle_index - 1
            elif middle_index + 1 < len(date_urls):
                second_index = middle_index + 1
            else:
                second_index = middle_index - 1

            another_date_url = date_urls[second_index]
            week_logger.warning(f'Chosen second date: {dates[second_index].isoformat()} (unix timestamp: {timestamps[second_index]})')
            submit_thread = threading.Thread(target=self.browsers[1].submit_form, args=(another_date_url, dates[second_index], timestamps[second_index]))
            self.form_submit_threads.append(submit_thread)
            submit_thread.start()

    def get_seconds_since_notification(self):
        return (dt.now() - self.last_send_message).total_seconds() if self.last_send_message else None

    def loop(self, week, max_attempts=None):
        n_attempt = 1
        total_time = 0
        week_logger = logging.getLogger(f"W-{week}")
        while not max_attempts or n_attempt <= max_attempts:
            start_time = dt.now()
            try:
                week_logger.debug(f'Attempt {n_attempt}')
                self.check_once(week, week_logger)
            except Exception as ex:
                week_logger.exception(ex)

            op_duration = (dt.now() - start_time).total_seconds()
            total_time += op_duration
            self.global_time_counter += op_duration
            self.global_req_counter += 1
            self.metrics.check_request_sent()
            if n_attempt % 100 == 0:
                week_logger.info(f'Average request time: {"{:.2f}".format(total_time/n_attempt)} s.')
                week_logger.info(f'Requests: {n_attempt}')
            n_attempt += 1
        week_logger.info("Finished checking")
        return week


    def start_loop(self, max_attempts=None, parallelism=1):
        weeks_to_scan = list(range(config.week_first, config.week_last + 1, 7))
        self.logger.info(f"Checking {len(weeks_to_scan)} weeks with parallelism of {parallelism}")
        all_weeks = weeks_to_scan * parallelism
        self.week_threads = []
        for week in all_weeks:
            week_thread = threading.Thread(target=self.loop, args=(week, max_attempts), daemon=True)
            week_thread.start()
            self.week_threads.append(week_thread)

        for week_thread in self.week_threads:
            try:
                week_thread.join()
            except Exception as exc:
                self.logger.exception(exc)
