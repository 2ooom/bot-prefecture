
import logging
import os
import sys
import json
import subprocess
import selenium
import threading
import requests

from users_data import form_data, anticaptcha_api_key
from utils import get_file_content, with_retry, user_agent
from lxml import html

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as wait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import *
from selenium.common.exceptions import TimeoutException
from datetime import datetime as dt

class Browser:
    SESSION_ID_COOKIE = 'eZSESSID'
    DUMPS_FOLDER = './dumps'
    NB_RETRIES = 10
    anticaptcha_js = get_file_content('./anticaptcha.js').replace('anti_captcha_api_key', anticaptcha_api_key)

    def __init__(self, config, form_data, tg_bot, proxies):
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.url_start = f'{self.url_base}/0'
        self.form_data = form_data
        self.tg_bot = tg_bot
        self.proxies = proxies
        self.driver = selenium.webdriver.Firefox()
        self.driver.maximize_window()
        self.logger = logging.getLogger("Browser")
        self.form_submit_started = False
        self.form_submit_lock = threading.Lock()
        self.session_id = ""
        self.proxy_index = 0

    def preload(self):
        self.set_preferences()
        self.go_to_start()
        self.accept_cookies()
        self.session_id = self.get_session_id()

    def set_preferences(self):
        self.driver.get("about:config")
        preferences_js = get_file_content('./firefox_preference.js')
        self.driver.execute_script(preferences_js)

    def get_start_url(self):
        return self.url_start

    def go_to_start(self):
        self.logger.info(f'Page 1: Loading "{self.get_start_url()}"')
        self.driver.get(self.get_start_url())

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
        session_cookie = list(filter(lambda c: c['name'] == Browser.SESSION_ID_COOKIE, cookies))
        return session_cookie[0]['value']

    def save_dump(self):
        timestamp = dt.now().isoformat()
        screenshot_fname = os.path.abspath(
            os.path.join(Browser.DUMPS_FOLDER, f'{timestamp}.png')
        )
        self.driver.save_screenshot(screenshot_fname)
        self.save_html(self.driver.page_source.encode('utf8'), timestamp)

        cookies_fname = os.path.abspath(
            os.path.join(Browser.DUMPS_FOLDER, f'{timestamp}-cookies.json')
        )
        with open(cookies_fname, 'w') as f:
            f.write(json.dumps(self.driver.get_cookies()))

    def save_html(self, html, name=None):
        filename = name if name else dt.now().isoformat()
        page_source_fname = os.path.abspath(
            os.path.join(Browser.DUMPS_FOLDER, f'{filename}.html')
        )
        with open(page_source_fname, 'wb') as f:
            f.write(html)

    def get_next_proxy_from_list(self):
        self.proxy_index = self.proxy_index + 1 if self.proxy_index < len(self.proxies) - 1 else 0
        return self.proxies[self.proxy_index]

    def post(self, url, data):
        proxy_url = self.get_next_proxy_from_list()
        return requests.post(
            url,
            cookies={Browser.SESSION_ID_COOKIE: self.session_id},
            headers={
                "ogirin": url,
                "user-agent": user_agent,
                "referer": url,
            },
            data=data,
            timeout=7,
            proxies={'http': proxy_url, 'https': proxy_url}
        )

    def update_internal_server_state(self):
        try:
            def step_0():
                self.logger.info('Step 0: Validating conditions')
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
                    self.save_html(page.content)
                    raise Exception("Wrong response. Retrying ...")
                if next_button[0].value != "Etape suivante":
                    self.save_html(page.content)
                    raise Exception("Step 0: Dates not available :(")
                return (tree, next_button)

            (tree, next_button) = with_retry(step_0, Browser.NB_RETRIES, self.logger)

            planning_input = tree.xpath("//input[@name='planning']")
            # for test only
            if len(planning_input):
                def step_1(next_button):
                    self.logger.info('Step 1: Selecting RDV type')
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
                        self.save_html(page.content)
                        raise Exception('Wrong response. Retrying ..')
                    if next_button[0].value != "Etape suivante":
                        self.save_html(page.content)
                        raise Exception("Step 1: Dates not available :(")
                    return (tree, next_button)

                (tree, next_button) = with_retry(step_1, Browser.NB_RETRIES, self.logger, next_button)
            else:
                self.logger.info('Step 1: Implicit')

            def step_3(next_button):
                self.logger.info('Step 3: Submitting form and implicitly choosing RDV type')
                page = self.post(
                    f"{self.url_base}/3",
                    {'nextButton': next_button[0].value}
                )
                tree = html.fromstring(page.content)
                etape4_active = tree.xpath("//img[contains(@src, '/etape_4r.png')]")
                if not len(etape4_active):
                    self.save_html(page.content)
                    raise Exception("Step 3: Dates not available :(")

            with_retry(step_3, Browser.NB_RETRIES, self.logger, next_button)
            return True
        except Exception as ex:
            self.logger.exception(ex)
            return False

    def update_internal_server_state_selenium(self):
        self.logger.info("Using selenium for fallback")
        self.logger.info('Step 0: Validating conditions')
        self.go_to_start()
        #checkbox
        self.click(self.driver.find_element_by_xpath('//*[@id="condition"]'))
        # next button
        self.click(self.driver.find_element_by_xpath('//*[@id="submit_Booking"]/input[1]'))
        next_button = wait(self.driver, 20).until(lambda d: d.find_element_by_xpath("//*[@value='Etape suivante']"))
        self.save_dump()
        planning = self.driver.find_elements_by_xpath("//input[@name='planning']")
        if len(planning):
            self.logger.info('Step 1: Selecting RDV type')
            self.click(planning[-1])
            self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
            # waiting for next page to appear
            wait(self.driver, 20).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_3r.png')]"))
            self.save_dump()
        else:
            self.logger.info('Step 1: Implicit')

        self.logger.info('Step 3: Submitting form and implicitly choosing RDV type')
        self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
        wait(self.driver, 20).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_4r.png')]"))
        self.logger.info('Step 4: Dates table')
        self.save_dump()

    def submit_form(self, date_url):
        with self.form_submit_lock:
            if self.form_submit_started:
                self.logger.info('Form submit already started. Skipping...')
                return
            else:
                self.logger.info('Form submitting started...')
                self.form_submit_started = True
        try:
            if not self.update_internal_server_state():
                self.update_internal_server_state_selenium()
            self.form_submit_started = True
            def step_4():
                self.logger.warning(f'Getting "{date_url}"...')
                self.driver.get(date_url)
                self.logger.warning('Step 4: enter captcha, click next and wait for next page to load')
                self.save_dump()

            with_retry(step_4, Browser.NB_RETRIES, self.logger)

            def step_5():
                # following these steps https://antcpt.com/eng/download/headless-captcha-solving.html
                self.driver.execute_script(Browser.anticaptcha_js)
                self.logger.info("Step 4. Added anticaptcha ")
                self.save_dump()
                found_element = wait(self.driver, 24*60*60).until(lambda d: d.find_element_by_xpath("//*[contains(@class, 'antigate_solver') and contains(@class, 'solved')] | //img[contains(@src, '/etape_8r.png')]"))
                self.save_dump()
                # captcha was solved automatically:
                if found_element.tag_name.lower() != 'img':
                    self.logger.info("Step 4. Captcha solved automatically.")
                    self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
                    wait(self.driver, 30).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_8r.png')]"))
                    self.save_dump()
                else:
                    self.logger.info("Step 4. Captcha solved manually.")

            with_retry(step_5, Browser.NB_RETRIES, self.logger)

            def step_6():
                # Personal data input loading
                self.logger.warning('Step 5: entering user data')
                for field, value in self.form_data.items():
                    try:
                        el = self.driver.find_element_by_xpath(f"//*[@name='{field}']")
                        el.clear()
                        el.send_keys(Keys.BACKSPACE * len(value) + value)
                    except Exception as err:
                        self.logger.error(f"Failed to enter '{field}''. Error: ")
                        self.logger.exception(err)

                self.click(self.driver.find_element_by_xpath("//input[@name='nextButton']"))
                # waiting for validation page
                wait(self.driver, 20).until(lambda d: d.find_element_by_xpath("//img[contains(@src, '/etape_9r.png')]"))

            with_retry(step_6, Browser.NB_RETRIES, self.logger)

            self.logger.warning('Step 6: validation')
            self.save_dump()
            self.click(self.driver.find_element_by_xpath("//input[@type='submit']"))
            self.logger.warning('Step 6: Submitted')
            print("All finished. Enter to restart")
            input()
        except Exception as err:
            self.logger.error("phfew. Error: ")
            self.logger.exception(err)
        print("Press enter twice to continue in case of false-positive...")
        input()
        print("Press enter again to confirm")
        input()
        self.go_to_start()
        with self.form_submit_lock:
            self.logger.warning('Resetting form submit status')
            self.form_submit_started = True

