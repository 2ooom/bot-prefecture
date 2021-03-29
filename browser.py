
import logging
import os
import time
import sys
import json
import subprocess
import selenium
import threading
import requests

from users_data import form_data, anticaptcha_api_key
from utils import get_file_content, with_retry, save_html, SESSION_ID_COOKIE, DUMPS_FOLDER
from lxml import html

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as wait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import *
from selenium.common.exceptions import TimeoutException
from datetime import datetime as dt

class Browser:
    NB_RETRIES = 5
    anticaptcha_js = get_file_content('./anticaptcha.js').replace('anti_captcha_api_key', anticaptcha_api_key)

    def __init__(self, config, form_data, tg_bot, http_client, wait_for_input=True):
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.url_start = f'{self.url_base}/0'
        self.form_data = form_data
        self.config = config
        self.tg_bot = tg_bot
        self.driver = selenium.webdriver.Firefox()
        self.driver.maximize_window()
        self.user_email = form_data['email']
        self.logger = logging.getLogger(f"Browser {self.user_email}")
        self.form_submit_started = False
        self.form_submit_lock = threading.Lock()
        self.session_id = ""
        self.http_client = http_client
        self.wait_for_input = wait_for_input
        self.rdv_taken = False
        self.updated_state = False

    def preload(self):
        self.set_preferences()
        self.go_to_start()
        self.accept_cookies()
        self.session_id = self.get_session_id()

    def set_preferences(self):
        self.driver.get("about:config")
        preferences_js = get_file_content('./firefox_preference.js')
        self.driver.execute_script(preferences_js)

    def go_to_start(self):
        self.logger.info(f'Page 1: Loading "{self.url_start}"')
        self.driver.get(self.url_start)
        #self.take_screenshot(f'🛫 Starting to watch for dates on this url: {self.url_start}')

    def log_step(self, message):
        self.logger.warning(message)
        self.tg_bot.send_to_admins("\n".join([f'`{self.user_email}`:', message]))

    def click(self, e):
        self.driver.execute_script(f'window.scrollTo(0, {e.location["y"]})')
        actions = ActionChains(self.driver)
        actions.move_to_element(e).click().perform()

    def accept_cookies(self):
        cookie_container = self.driver.find_elements_by_xpath('//*[@id="cookies-banner"]')
        if cookie_container and "none" not in cookie_container[0].get_attribute('style'): 
            self.click(cookie_container[0].find_element_by_xpath('.//a[text()="Accepter"]'))
            self.logger.info('Page 1: cookies accepted')

    def get_session_id(self):
        cookies = self.driver.get_cookies()
        session_cookie = list(filter(lambda c: c['name'] == SESSION_ID_COOKIE, cookies))
        return session_cookie[0]['value']

    def save_step(self, comment=''):
        self.logger.warning(comment)
        self.take_screenshot(comment)
        html_path = save_html(self.driver.page_source.encode('utf8'))
        self.tg_bot.send_to_admins("\n".join([f'`{self.user_email}`:', comment]), html_path, 'html')

    def take_screenshot(self, comment=''):
        timestamp = dt.now().isoformat()
        screenshot_path = os.path.abspath(
            os.path.join(DUMPS_FOLDER, f'{timestamp}.png')
        )
        self.driver.save_screenshot(screenshot_path)
        self.tg_bot.send_to_admins("\n".join([f'`{self.user_email}`:', comment]), screenshot_path, 'photo')

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
        print('task_id', task_id)
        print("Anticaptcha response: ", task_resp.json())
        g_captcha_response = None
        for i in range(0, 60*2*2):
            resp = requests.post('https://api.anti-captcha.com/getTaskResult', json={
                "clientKey": anticaptcha_api_key,
                "taskId": task_id
            }).json()
            print('resp[status]', resp['status'])
            print("Anticaptcha response: ", resp)
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
        try:
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
                raise Exception('Step 4: Failed to load')

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
                raise Exception('Step 6: Next button not found')
            if next_button[0].value != "Etape suivante":
                save_html(page.content)
                raise Exception("Step 6: Dates not available :(")
            self.log_step('✅ Step 6: Anticaptcha accepted')
            self.log_step('Step 8: Submitting form')
            page = self.post(
                f"{self.url_base}/8",
                {
                    **self.form_data,
                    'nextButton': 'Etape+suivante'
                })
            tree = html.fromstring(page.content)
            message_sent = tree.xpath("//li[contains(text(), 'Un message électronique vous a été envoyé.')]")
            if not len(message_sent):
                save_html(page.content)
                raise Exception('Step 8: Message not sent')
            self.log_step('✅ Step 8: Submitted. Check email')
            return True
        except Exception as ex:
            self.log_step('☠️ Booking date via http did not work. Falling back to selenium...')
            self.logger.exception(ex)
            return False

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
            date_booked = self.book_date(date_url)
            if not date_booked:
                def step_4():
                    self.log_step(f'Step 4: Getting "{date_url}"')
                    self.driver.get(date_url)
                    self.save_step(f'Step 4: Loaded {date_url}')

                with_retry(step_4, Browser.NB_RETRIES, self.logger)

                # following these steps https://antcpt.com/eng/download/headless-captcha-solving.html
                self.driver.execute_script(Browser.anticaptcha_js)
                self.save_step("Step 4. Added anticaptcha ")
                found_element = wait(self.driver, 5*60).until(lambda d: d.find_element_by_xpath("//*[contains(@class, 'antigate_solver') and contains(@class, 'solved')] | //img[contains(@src, '/etape_8r.png')]"))
                # captcha was solved automatically:
                if found_element.tag_name.lower() != 'img':
                    self.log_step("Step 4. Captcha solved automatically going to next page.")
                    self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
                    wait(self.driver, 30).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_8r.png')]"))
                else:
                    self.log_step("Step 4. Captcha solved manually.")

                self.log_step('Step 5: entering user data')

                # Personal data input loading
                for field, value in self.form_data.items():
                    try:
                        el = self.driver.find_element_by_xpath(f"//*[@name='{field}']")
                        el.clear()
                        el.send_keys(Keys.BACKSPACE * len(value) + value)
                    except Exception as err:
                        self.logger.error(f"Failed to enter '{field}''. Error: ")
                        self.logger.exception(err)

                self.save_step('Step 5: entered form data')
                self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
                # waiting for validation page
                wait(self.driver, 20).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_9r.png')]"))

                self.save_step('Step 6: Validation')
                self.click(self.driver.find_element_by_xpath("//input[@type='submit']"))
                self.save_step('Step 6: Submitted')
                wait(self.driver, 20).until_not(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_9r.png')]"))

            self.save_step(f'💚 RDV Taken @ `{date_chosen}` (unix timestamp: {timestamp})')
            self.rdv_taken = True
        except Exception as err:
            self.logger.error("phfew. Error: ")
            self.logger.exception(err)
        if self.wait_for_input:
            print("Waiting 1 min just in case")
            time.sleep(60)
        with self.form_submit_lock:
            self.logger.warning('Resetting form submit status')
            self.form_submit_started = False

