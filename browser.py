
import logging
import os
import time
import sys
import json
import subprocess
import threading
import requests

from http_client import HttpClient
from users_data import form_data, anticaptcha_api_key
from utils import get_file_content, save_html, SESSION_ID_COOKIE, DUMPS_FOLDER
from lxml import html
from datetime import datetime as dt

class Browser:
    NB_RETRIES = 5

    def __init__(self, config, form_data, tg_bot, http_client):
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.url_start = f'{self.url_base}/0'
        self.form_data = form_data
        self.config = config
        self.tg_bot = tg_bot
        self.user_email = form_data['email']
        self.logger = logging.getLogger(f"Browser {self.user_email}")
        self.form_submit_started = False
        self.form_submit_lock = threading.Lock()
        self.logger.info(f'Page 1: Loading "{self.url_start}"')
        response = requests.get(self.url_start, headers={"user-agent": HttpClient.USER_AGENT})
        self.session_id = response.cookies[SESSION_ID_COOKIE]
        self.log_step(f'🛫 Starting to watch for dates on {self.url_start}\nSessionId: `{self.session_id}`')
        self.http_client = http_client
        self.rdv_taken = False
        self.updated_state = False

    def log_step(self, message):
        self.logger.warning(message)
        self.tg_bot.send_to_admins("\n".join([f'`{self.user_email}`:', message]))

    def post(self, url, data):
        return self.http_client.req(
            'post',
            url,
            max_retries=Browser.NB_RETRIES,
            cookies={SESSION_ID_COOKIE: self.session_id},
            headers={
                "ogirin": url,
                "referer": url,
            },
            data=data
        )

    def update_internal_server_state(self):
        if self.updated_state:
            self.log_step('Step 0-3: skipping. Internal server state already updated.')
            return
        self.log_step('Step 0: Validating conditions')
        page = self.post(
            self.url_start,
            {
                'condition': 'on',
                'nextButton': 'Effectuer+une+demande+de+rendez-vous',
            }
        )
        tree = html.fromstring(page.content)
        next_button = tree.xpath("//input[@name='nextButton']")
        if not len(next_button):
            save_html(page.content)
            raise Exception("Step 0: Next button not found")
        if next_button[0].value != "Etape suivante":
            save_html(page.content)
            raise Exception("Step 0: Dates not available :(")

        planning_input = tree.xpath("//input[@name='planning']")
        # for test only
        if len(planning_input):
            self.log_step('Step 1: Selecting RDV type')
            page = self.post(
                f"{self.url_base}/1",
                {
                    'planning': planning_input[-1].attrib['value'],
                    'nextButton': next_button[0].value,
                }
            )
            tree = html.fromstring(page.content)
            next_button = tree.xpath("//input[@name='nextButton']")
            if not len(next_button):
                save_html(page.content)
                raise Exception('Step 1: Next button not found')
            if next_button[0].value != "Etape suivante":
                save_html(page.content)
                raise Exception("Step 1: Dates not available :(")
        else:
            self.logger.info('Step 1: Implicit')

        self.log_step('Step 3: Submitting form and implicitly choosing RDV type')
        page = self.post(
            f"{self.url_base}/3",
            {'nextButton': 'Etape suivante'}
        )
        tree = html.fromstring(page.content)
        etape4_active = tree.xpath("//img[contains(@src, '/etape_4r.png')]")
        if not len(etape4_active):
            save_html(page.content)
            raise Exception("Step 3: Dates not available :(")
        self.updated_state = True

    def get_captcha_solution(self):
        task_resp = requests.post('https://api.anti-captcha.com/createTask', json={
            'clientKey' : anticaptcha_api_key,
            'task':
                {
                    "type":"RecaptchaV2TaskProxyless",
                    "websiteURL": self.config.url,
                    "websiteKey": self.config.recatcha_sitekey
                }
        })
        task_id = task_resp.json()['taskId']
        g_captcha_response = None
        for i in range(0, 60*2*2):
            resp = requests.post('https://api.anti-captcha.com/getTaskResult', json={
                "clientKey": anticaptcha_api_key,
                "taskId": task_id
            }).json()
            if 'status' in resp and resp['status'] == 'ready':
                g_captcha_response = resp['solution']['gRecaptchaResponse']
                break
            time.sleep(0.5)
            if i % 20 == 0:
                self.logger.warning(f'Anticaptcha status: {resp["status"]}. waiting 10 sec..')

        if not g_captcha_response:
            raise Exception("Anticaptcha not solved in 2 min.")
        return g_captcha_response

    def book_date(self, date_url):
        self.log_step(f'Step 4: Via Http getting "{date_url}"')
        page = self.http_client.get(
            date_url,
            max_retries=Browser.NB_RETRIES,
            cookies={SESSION_ID_COOKIE: self.session_id},
            headers={
                "ogirin": date_url,
                "referer": date_url,
            })
        if not page:
            raise Exception('☠️ Step 4: Failed to load')

        self.log_step(f'✅ Step 4: Via Http loaded {date_url}')
        self.log_step('Step 6: Solving anticaptcha')
        g_captcha_response = self.get_captcha_solution()
        self.log_step('✅ Step 6: Anticaptcha solved')
        page = self.post(
            f"{self.url_base}/6",
            {
                'g-recaptcha-response': g_captcha_response,
                'nextButton': 'Etape+suivante'
            })
        tree = html.fromstring(page.content)
        next_button = tree.xpath("//input[@name='nextButton']")
        if not len(next_button):
            save_html(page.content)
            raise Exception('☠️ Step 6: Next button not found')
        if next_button[0].value != "Etape suivante":
            save_html(page.content)
            raise Exception("☠️ Step 6: Dates not available :(")
        self.log_step('✅ Step 6: Anticaptcha accepted')
        self.log_step('Step 8: Submitting form')
        page = self.post(
            f"{self.url_base}/8",
            {
                **self.form_data,
                'nextButton': 'Etape+suivante'
            })
        tree = html.fromstring(page.content)
        message_sent = tree.xpath("//li[contains(text(), 'Vous disposez de 60 minutes pour confirmer')]")
        if not len(message_sent):
            save_html(page.content)
            self.log_step('☠️ Step 8: Not submitted :(')
            raise Exception('☠️ Step 8: Message not sent')
        self.log_step('✅ Step 8: Submitted. Check email')

    def submit_form(self, date_url, date_chosen, timestamp):
        with self.form_submit_lock:
            if self.form_submit_started:
                self.logger.info('Form submit already started. Skipping...')
                return
            else:
                self.form_submit_started = True
        try:
            self.log_step(f'Form submit started. Date: {date_chosen} (unix timestamp: {timestamp})')
            self.update_internal_server_state()
            self.book_date(date_url)

            self.log_step(f'💚 RDV Taken @ `{date_chosen}` (unix timestamp: {timestamp})')
            self.rdv_taken = True
        except Exception as err:
            self.logger.error("phfew. Error: ")
            self.logger.exception(err)
        with self.form_submit_lock:
            self.logger.warning('Resetting form submit status')
            self.form_submit_started = False

