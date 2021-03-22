#!/usr/bin/env python3

import logging
import time
import os
import sys
import subprocess
import concurrent.futures
import requests
import threading

from browser import Browser
from telegram_bot import TelegramBot
from users_data import form_data, form_data_dp, form_data_op, anticaptcha_api_key, telegram_bot_token
from config import config
from utils import user_agent

from datetime import datetime as dt
from lxml import html
from collections import defaultdict

DB_PATH = './bot_state.json'
NOTIFICATIONS_DELAY = 7
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

def get_next_proxy_from_list():
    global proxy_index
    while True:
        proxy_index = proxy_index + 1 if proxy_index < len(proxies) - 1 else 0
        proxy = proxies[proxy_index]
        if proxy not in faulty_proxies:
            break
    return proxy

def get_proxies(filepath):
    proxies = []
    with open(filepath, "r") as f:
        while True:
            line = f.readline()
            if not line:
                break
            proxies.append(line.strip())
    logger.info(f"{len(proxies)} proxies loaded")
    return proxies

def delist_proxy(proxy_endpoint):
    faulty_proxies.add(proxy_endpoint)
    logger.info(f'Proxy {proxy_endpoint} is faulty - delisting')
    with open('./proxies-working.txt', 'w') as f:
        for existing_proxy in proxies:
            if existing_proxy not in faulty_proxies:
                f.writelines([proxy_endpoint])

def check_once(proxy_endpoint, week, logger, browsers):
    global last_send_message
    proxy_url = f"http://{proxy_endpoint}"
    date_table = requests.get(
        f"{config.url}/ezjscore/call/bookingserver::planning::assign::{config.form_id}::{config.ajax_id}::{week}",
        timeout=7,
        headers={"user-agent": user_agent},
        proxies={'http': proxy_url, 'https': proxy_url}
    )
    if not date_table.ok:
        if date_table.status_code == 403:
            delist_proxy(proxy_endpoint)
        elif date_table.status_code == 502:
            logger.warning('502 - Bad gateway')
        else:
            logger.error(f'Error {date_table.status_code}]')
            browsers[0].save_html(date_table.content)
        return

    tree = html.fromstring(date_table.content)
    date_links = tree.xpath(f".//a[contains(@href, 'booking/create/{config.form_id}/5')]")
    dates_period = tree.xpath(".//th[@colspan='7']")[0].text.strip()
    if not date_links:
        logger.info(f'No dates found. {dates_period}')
        return
    date_urls = list(map(lambda l: l.attrib["href"], date_links))
    date_urls.sort()
    timestamps = list(map(lambda url: int(url.split("/")[-1]), date_urls))
    dates = list(map(lambda ts: dt.fromtimestamp(ts), timestamps))
    logger.warning('Dates found:')
    time_by_date = defaultdict(list)
    for d in dates:
        date_str = d.strftime("%d %b")
        time_str = d.strftime("%H:%M;")
        time_by_date[date_str].append(time_str)

    times_str = []
    for day, times in time_by_date.items():
        all_times = " ".join(times)
        times_str.append(f'🗓 *{day}*\n {all_times}\n')
        logger.warning(f'{day}: {all_times}')

    if not last_send_message or (dt.now() - last_send_message).total_seconds() >= NOTIFICATIONS_DELAY:
        dates_list = "\n".join(times_str)
        tg_bot.send_all(f"""⚡️⚡️⚡️ {len(dates)} date(s) found ⚡️⚡️⚡️ :
*{dates_period}*

{dates_list}

*Book RDV now by clicking*:
[{start_url}]({start_url})
""")
        last_send_message = dt.now()
        say_text = 'Dates Available.'
        subprocess.Popen(['say', f'"{say_text}"'])
    else:
        logger.info(f'Not sending notification {(dt.now() - last_send_message).total_seconds()} seconds elapsed since previous')

    middle_index = int(len(date_urls) / 2)
    date_url = date_urls[middle_index]
    logger.warning(f'Chosen first date: {dates[middle_index].isoformat()} (unix timestamp: {timestamps[middle_index]})')
    submit_thread = threading.Thread(target=browsers[0].submit_form, args=(date_url,))
    form_submit_threads.append(submit_thread)
    submit_thread.start()
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
        logger.warning(f'Chosen second date: {dates[second_index].isoformat()} (unix timestamp: {timestamps[second_index]})')
        submit_thread = threading.Thread(target=browsers[1].submit_form, args=(another_date_url,))
        form_submit_threads.append(submit_thread)
        submit_thread.start()

def loop(week, browsers, max_attempts=None):
    global global_req_counter
    global global_time_counter
    logger = logging.getLogger(f"W-{week}")
    n_attempt = 1
    total_time = 0
    while not max_attempts or n_attempt <= max_attempts:
        start_time = dt.now()
        try:
            proxy_endpoint = get_next_proxy_from_list()
            logger.info(f'Attemp {n_attempt}. Proxy [{proxy_index}/{len(proxies) - 1}]: {proxy_endpoint}')
            check_once(proxy_endpoint, week, logger, browsers)
        except Exception as ex:
            logger.exception(ex)

        op_duration = (dt.now() - start_time).total_seconds()
        total_time += op_duration
        global_time_counter += op_duration
        global_req_counter += 1
        if n_attempt % 20 == 0:
            logger.info(f'Average request time: {"{:.2f}".format(total_time/n_attempt)} s.')
            logger.info(f'Requests: {n_attempt}')
            logger.info(f'Total requests: {global_req_counter}')
            logger.info(f'Global Average request time: {"{:.2f}".format(global_time_counter/global_req_counter)} s.')
        n_attempt += 1
    logger.info("Finished checking")
    return week


def start_loop(browsers, max_attempts=None, parallelism=1):
    weeks_to_scan = list(range(config.week_first, config.week_last + 1, 7))
    logger.info(f"Checking {len(weeks_to_scan)} weeks with parallelism of {parallelism}")
    all_weeks = weeks_to_scan * parallelism
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_weeks)) as executor:
        week_futures = map(lambda week: executor.submit(loop, week, browsers, max_attempts), all_weeks)
        for future in concurrent.futures.as_completed(week_futures):
            try:
                week = future.result()
            except Exception as exc:
                logger.exception(exc)

setup_logging(LOG_PATH)
logger = logging.getLogger("Global")
faulty_proxies = set()
proxies = get_proxies("./proxies.txt")
proxy_index = 0

global_req_counter = 0
global_time_counter = 0


tg_bot = TelegramBot(telegram_bot_token, DB_PATH)
browsers = [
    Browser(config, form_data_op, tg_bot, proxies),
    Browser(config, form_data_dp, tg_bot, proxies)
]
start_url = browsers[0].get_start_url()

for br in browsers:
    br.preload()

last_send_message = None
form_submit_threads = []
if __name__ == "__main__":
    start_loop(
        browsers,
        max_attempts=int(sys.argv[1]) if len(sys.argv) > 1 else None,
        parallelism=1
    )
    logger.info(f"Waiting for {len(form_submit_threads)} submit actions to finish")
    for th in form_submit_threads:
        th.join()

    logger.info("Done. Exiting")