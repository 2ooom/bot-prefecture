
import logging
import time
import threading

from browser import Browser
from http_client import HttpClient
from users_data import form_data

from datetime import datetime as dt
from lxml import html
from collections import defaultdict

class Watcher:
    DELAY_IF_NOT_FOUND_SEC = 1
    NOTIFICATIONS_DELAY = 7

    def __init__(self, tg_bot, http_client, browsers, metrics, config, parallelism=1):
        self.logger = logging.getLogger(Watcher.__name__)
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.start_url = f'{self.url_base}/0'
        self.http_client = http_client
        self.tg_bot = tg_bot
        self.browsers = browsers
        self.metrics = metrics
        self.config = config
        self.parallelism = parallelism
        (self.planning_ids, self.planning_titles) = self.get_all_planning_ids()
        self.weeks_to_scan = []
        for planning_id in self.planning_ids:
            for week in range(config.week_first, config.week_last + 1, 7):
                self.weeks_to_scan.append((week, planning_id))

        self.base_watch_url = f"{config.url}/ezjscore/call/bookingserver::planning::assign::{config.form_id}"
        self.global_req_counter = 0
        self.global_failed_req_counter = 0
        self.global_time_counter = 0
        self.form_submit_threads = []

    def get_all_planning_ids(self):
        planning = self.http_client.get(f'{self.url_base}/1')
        tree = html.fromstring(planning.content)
        planning_inputs = tree.xpath("//input[@name='planning']")
        planning_ids = list(map(lambda planning_input: planning_input.attrib['value'], planning_inputs))
        planning_titles = {}
        for planning_id in planning_ids:
            label = tree.xpath(f"//label[@for='planning{planning_id}']")[0].text
            planning_titles[planning_id] = label
        self.logger.info(f'Found {len(planning_inputs)} planning id(s): {"; ".join(planning_ids)}')
        return (planning_ids, planning_titles)

    def check_once(self, week, planning_id, week_logger):
        date_table = self.http_client.get(f'{self.base_watch_url}::{planning_id}::{week}')
        if not date_table:
            self.global_failed_req_counter += 1
            return
        tree = html.fromstring(date_table.content)
        date_links = tree.xpath(f".//a[contains(@href, 'booking/create/{self.config.form_id}/5')]")
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

        middle_index = int(len(date_urls) / 2)
        date_url = date_urls[middle_index]
        week_logger.warning(f'Chosen first date: {dates[middle_index].isoformat()} (unix timestamp: {timestamps[middle_index]})')
        if not self.browsers:
            self.logger.warning(f"All programmed RDVs taken (total {len(self.browsers)}). Skipping submit")
            return
        if len(self.browsers) == 1 and len(self.weeks_to_scan) == 1 and self.parallelism == 1:
            self.logger.warning("Single RDV and single thread. Stop checking, and book RDV synchronously.")
            self.browsers[0].submit_form(date_url, dates[middle_index], timestamps[middle_index], form_data[0])
        else:
            submit_thread = threading.Thread(target=self.browsers[0].submit_form_with_lock, args=(date_url, dates[middle_index], timestamps[middle_index], form_data[0]))
            self.form_submit_threads.append(submit_thread)
            submit_thread.start()
            if len(date_urls) > 1 and len(self.browsers) > 1:
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
                submit_thread = threading.Thread(target=self.browsers[1].submit_form, args=(another_date_url, dates[second_index], timestamps[second_index], form_data[1]))
                self.form_submit_threads.append(submit_thread)
                submit_thread.start()

            time.sleep(Watcher.NOTIFICATIONS_DELAY)

    def loop(self, week, planning_id, max_attempts=None):
        n_attempt = 1
        total_time = 0
        week_logger = logging.getLogger(f"W-{week}-{planning_id}")
        while not max_attempts or n_attempt <= max_attempts:
            start_time = dt.now()
            try:
                week_logger.debug(f'Attempt {n_attempt}')
                self.check_once(week, planning_id, week_logger)
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


    def start_loop(self, max_attempts=None):
        self.logger.info(f"Checking {len(self.weeks_to_scan)} weeks with parallelism of {self.parallelism}")
        all_weeks = self.weeks_to_scan * self.parallelism
        self.week_threads = []
        for (week, planning_id) in all_weeks:
            week_thread = threading.Thread(target=self.loop, args=(week, planning_id, max_attempts), daemon=True)
            week_thread.start()
            self.week_threads.append(week_thread)

        for week_thread in self.week_threads:
            try:
                week_thread.join()
            except Exception as exc:
                self.logger.exception(exc)
