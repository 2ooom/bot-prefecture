
import logging
import time
import threading

from browser import Browser
from watcher import Watcher
from users_data import form_data
from datetime import datetime as dt
from lxml import html
from utils import save_html
from collections import defaultdict

class WatcherMultislot(Watcher):

    def __init__(self, tg_bot, http_client, metrics, config, parallelism=1):
        self.logger = logging.getLogger(WatcherMultislot.__name__)
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.start_url = f'{self.url_base}/0'
        self.http_client = http_client
        self.tg_bot = tg_bot
        self.metrics = metrics
        self.config = config
        self.parallelism = parallelism
        (self.slots_to_scan, self.planning_titles) = self.get_all_planning_ids()
        self.global_req_counter = 0
        self.global_failed_req_counter = 0
        self.global_time_counter = 0
        self.form_submit_threads = []
        self.form_data_index = 0

    def check_once(self, browser, planning_id, slot_logger):
        slot_logger.debug('Step 3: Submitting form and implicitly choosing RDV type')
        if not browser.check_planning_dates(planning_id, self.planning_titles[planning_id]):
            self.global_failed_req_counter += 1
            time.sleep(Watcher.DELAY_IF_NOT_FOUND_SEC)
            return

        if self.form_data_index < len(form_data):
            g_captcha_response = browser.choose_first_date_while_solving_captcha()
            browser.book_date(g_captcha_response, form_data[self.form_data_index])
            self.tg_bot.send_to_admins(f'💚 RDV Taken for `{form_data[self.form_data_index]["email"]}` check email')
            self.form_data_index += 1
        else:
            time.sleep(Watcher.NOTIFICATIONS_DELAY)

    def loop(self, planning_id, max_attempts=None):
        n_attempt = 1
        total_time = 0
        slot_logger = logging.getLogger(f"S-{planning_id}")
        browser = Browser(self.config, self.tg_bot, self.http_client)
        while not max_attempts or n_attempt <= max_attempts:
            start_time = dt.now()
            try:
                slot_logger.debug(f'Attempt {n_attempt}')
                self.check_once(browser, planning_id, slot_logger)
            except Exception as ex:
                slot_logger.exception(ex)

            op_duration = (dt.now() - start_time).total_seconds()
            total_time += op_duration
            self.global_time_counter += op_duration
            self.global_req_counter += 1
            self.metrics.check_request_sent()
            if n_attempt % 100 == 0:
                slot_logger.info(f'Average request time: {"{:.2f}".format(total_time/n_attempt)} s.')
                slot_logger.info(f'Requests: {n_attempt}')
            n_attempt += 1
        slot_logger.info("Finished checking")


    def start_loop(self, max_attempts=None):
        self.logger.info(f"Checking {len(self.slots_to_scan)} slots with parallelism of {self.parallelism}")
        all_slots = self.slots_to_scan * self.parallelism
        self.slot_threads = []
        for planning_id in all_slots:
            slot_thread = threading.Thread(target=self.loop, args=(planning_id, max_attempts), daemon=True)
            slot_thread.start()
            self.slot_threads.append(slot_thread)

        for slot_thread in self.slot_threads:
            try:
                slot_thread.join()
            except Exception as exc:
                self.logger.exception(exc)
