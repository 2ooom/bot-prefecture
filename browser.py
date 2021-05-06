
import logging
import time
import os
import threading
import requests
import concurrent.futures

from http_client import HttpClient
from users_data import anticaptcha_api_key
from utils import save_html, SESSION_ID_COOKIE, WEBSITE_HOSTNAME
from lxml import html

class Browser:
    NB_RETRIES = 5
    NB_PARALLEL_CAPCHAS = 3

    def __init__(self, config, tg_bot, http_client):
        self.url_base = f'{config.url}/booking/create/{config.form_id}'
        self.url_start = f'{self.url_base}/0'
        self.config = config
        self.tg_bot = tg_bot
        self.logger = logging.getLogger("Browser")
        self.form_submit_started = False
        self.form_submit_lock = threading.Lock()
        self.logger.info(f'Page 1: Loading "{self.url_start}"')
        response = requests.get(self.url_start, headers=HttpClient.DEFAULT_HEADERS)
        self.session_id = response.cookies[SESSION_ID_COOKIE]
        self.log_step(f'🛫 Starting to watch for dates on {self.url_start}\nSessionId: `{self.session_id}`')
        self.http_client = http_client
        self.capcha_executor = concurrent.futures.ThreadPoolExecutor(max_workers=Browser.NB_PARALLEL_CAPCHAS)

    def log_step(self, message):
        self.logger.warning(message)
        lines = [
            f'🖥 `Host: {os.environ.get(WEBSITE_HOSTNAME)}; SessionId: {self.session_id}`:',
            message
        ]
        self.tg_bot.send_to_admins("\n".join(lines))

    def post(self, url, data, first_attempt_with_proxy=False):
        return self.http_client.req(
            'post',
            url,
            max_retries=Browser.NB_RETRIES,
            cookies={SESSION_ID_COOKIE: self.session_id},
            headers={
                "origin": url,
                "referer": url,
            },
            data=data,
            first_attempt_with_proxy=first_attempt_with_proxy
        )

    def check_planning_dates(self, planning_id, planning_title):
        self.logger.debug(f'Step 1: Checking planning {planning_id}')
        page = self.post(
            f"{self.url_base}/1",
            {
                'planning': str(planning_id),
                'nextButton': 'Etape suivante',
            },
            first_attempt_with_proxy=True
        )
        if not page:
            return page
        tree = html.fromstring(page.content)
        etape3_active = tree.xpath("//img[contains(@src, '/etape_3r.png')]")
        etape4_active = tree.xpath("//img[contains(@src, '/etape_4r.png')]")
        if len(etape3_active) or len(etape4_active):
            self.log_step(f'✅ Step 1: Dates available for "{planning_title}"')
            save_html(page.content)
            return page
        finish_button = tree.xpath("//input[@name='finishButton']")
        if finish_button[0].value == "Terminer":
            self.logger.debug(f'Step 1: No dates {planning_title}')
            return page
        self.log_step(f'❓ Step 1: Anomaly detected for {planning_title}. Dumping html.')
        save_html(page.content)
        return page

    def accept_conditions(self):
        self.logger.info('Step 0: Validating conditions')
        page = self.post(
            self.url_start,
            {
                'condition': 'on',
                'nextButton': 'Effectuer+une+demande+de+rendez-vous',
            }
        )
        if not page:
            raise Exception('Conditions not accepted. Bad request')
        tree = html.fromstring(page.content)
        next_button = tree.xpath("//input[@name='nextButton']")
        if not len(next_button):
            save_html(page.content)
            raise Exception("Step 0: Next button not found")
        return page

    def update_internal_server_state(self, previous_page):
        tree = html.fromstring(previous_page.content)
        forms = tree.xpath("//form[@id='FormBookingCreate']")
        if len(forms) and forms[0].attrib['action'].endswith('/4'):
            save_html(previous_page.content)
            self.log_step('✅ Step 0 and 3: Accepted conditions and RDV type chosen')
            return

        next_button = tree.xpath("//input[@name='nextButton']")
        if next_button[0].value != "Etape suivante":
            save_html(page.content)
            raise Exception("Step 0: Dates not available :(")
        self.log_step('✅ Step 0: Accepted conditions')

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
        self.log_step('✅  Step 3: Submitted')
        save_html(page.content)

    def choose_first_available(self):
        self.log_step('Step 4: Choosing the first timeslot available')
        page = self.post(
            f"{self.url_base}/4",
            {
                'nextButton': 'Première+plage+horaire+libre'
            }
        )
        tree = html.fromstring(page.content)
        etape6_active = tree.xpath("//img[contains(@src, '/etape_6r.png')]")
        if not len(etape6_active):
            save_html(page.content)
            raise Exception("Step 4: Dates not available :(")
        save_html(page.content)
        date_time = tree.xpath("//*[@id='inner_Booking']/fieldset")[0].text_content()
        self.log_step('\n'.join(['✅  Step 4: Chosen date', f'```{date_time}```']))

    def get_captcha_solution(self, index):
        task_resp = requests.post('https://api.anti-captcha.com/createTask', json={
            'clientKey' : anticaptcha_api_key,
            'task':
                {
                    "type":"RecaptchaV2TaskProxyless",
                    "websiteURL": self.config.url,
                    "websiteKey": self.config.recapcha_sitekey
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
            raise Exception(f"Anticaptcha `{index}` `{task_id}` not solved in 2 min.")
        self.log_step(f'✅ Anticaptcha `{index}` `{task_id}` solved')
        return g_captcha_response

    def update_state_while_solving_captcha(self, date_url):
        self.log_step(f'Solving {Browser.NB_PARALLEL_CAPCHAS} anticaptcha(s) in parallel')
        solvers = [self.capcha_executor.submit(self.get_captcha_solution, i) for i in range(Browser.NB_PARALLEL_CAPCHAS)]
        page = self.accept_conditions()
        self.update_internal_server_state(page)
        self.log_step(f'Step 4: Via Http getting "{date_url}"')
        page = self.http_client.get(
            date_url,
            max_retries=Browser.NB_RETRIES,
            cookies={SESSION_ID_COOKIE: self.session_id},
            headers={"origin": date_url, "referer": date_url},
            first_attempt_with_proxy=False)
        if not page:
            raise Exception('☠️ Step 4: Failed to load')

        tree = html.fromstring(page.content)
        date_time = tree.xpath("//*[@id='inner_Booking']/fieldset")[0].text_content()
        self.log_step('\n'.join([f'✅ Step 4: Via Http loaded {date_url}:', f'```{date_time}```']))
        (solved, _) = concurrent.futures.wait(solvers, return_when='FIRST_COMPLETED')
        return list(solved)[0].result()

    def choose_first_date_while_solving_captcha(self, page):
        self.log_step(f'Solving {Browser.NB_PARALLEL_CAPCHAS} anticaptcha(s) in parallel')
        solvers = [self.capcha_executor.submit(self.get_captcha_solution, i) for i in range(Browser.NB_PARALLEL_CAPCHAS)]
        self.update_internal_server_state(page)
        self.choose_first_available()
        (solved, _) = concurrent.futures.wait(solvers, return_when='FIRST_COMPLETED')
        return list(solved)[0].result()

    def book_date(self, g_captcha_response, form_data):
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
        user_email = form_data['email']
        self.log_step(f'Step 8: Submitting form for `{user_email}`')
        page = self.post(
            f"{self.url_base}/8",
            {
                **form_data,
                'nextButton': 'Etape+suivante'
            })
        tree = html.fromstring(page.content)
        message_sent = tree.xpath("//li[contains(text(), 'Vous disposez de') and contains(text(), 'minutes pour confirmer')]")
        if not len(message_sent):
            save_html(page.content)
            self.log_step('☠️ Step 8: Not submitted :(')
            raise Exception('☠️ Step 8: Message not sent')
        self.log_step('✅ Step 8: Submitted. Check email `{user_email}`')

    def submit_form(self, date_url, date_chosen, timestamp, form_data):
        try:
            self.log_step(f'Form submit started. Date: {date_chosen} (unix timestamp: {timestamp})')
            g_captcha_response = self.update_state_while_solving_captcha(date_url)
            self.book_date(g_captcha_response, form_data)

            self.log_step(f'💚 RDV Taken @ `{date_chosen}` (unix timestamp: {timestamp})')
        except Exception as err:
            self.logger.error("phfew. Error: ")
            self.logger.exception(err)

    def submit_form_with_lock(self, date_url, date_chosen, timestamp, form_data):
        with self.form_submit_lock:
            if self.form_submit_started:
                self.logger.info('Form submit already started. Skipping...')
                return
            else:
                self.form_submit_started = True
        self.submit_form(date_url, date_chosen, timestamp, form_data)
        with self.form_submit_lock:
            self.logger.warning('Resetting form submit status')
            self.form_submit_started = False
