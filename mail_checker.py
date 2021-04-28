import logging
import json
import time
import threading
from email import message_from_bytes
import base64
import requests

import google.auth
import googleapiclient.discovery

from lxml import html
from http_client import HttpClient
from utils import save_html, SESSION_ID_COOKIE

class MailChecker:
    DELAY_IN_SECONDS = 5 * 60

    def __init__(self, store, email, config, tg_bot):
        self.store = store
        self.email = email
        self.config = config
        self.tg_bot = tg_bot
        self.logger = logging.getLogger(f"MailChecker {email}")
        self.check_thread = None
        self.service = None

    def start_loop(self, max_attempts=None):
        self.check_thread = threading.Thread(target=self.loop, args=(max_attempts, ), daemon=True)
        self.check_thread.start()
        self.log_step(f'Started to checking email every {MailChecker.DELAY_IN_SECONDS / 60} min')
        return self.check_thread

    def log_step(self, message):
        self.logger.warning(message)
        self.tg_bot.send_to_admins("\n".join([f'✉️ `{self.email}`:', message]))

    def loop(self, max_attempts):
        self.logger.info('Fetching and validating credentials')
        credentials = self.store.get_credentials(self.email)
        self.service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials)
        self.logger.info(f'Credentials validated. Starting to regular check:')
        n_attempt = 1
        while not max_attempts or n_attempt <= max_attempts:
            try:
                self.check_once()
            except Exception as ex:
                self.logger.error('Checking failed. Error:')
                self.logger.exception(ex)
            time.sleep(MailChecker.DELAY_IN_SECONDS)
            n_attempt += 1

    def check_once(self):
        unread_msgs = self.service.users().messages().list(userId='me', labelIds=['UNREAD', 'INBOX'], q='subject:"Demande de rendez-vous en attente de confirmation"').execute()
        if unread_msgs['resultSizeEstimate'] <= 0:
            self.logger.info('No new messages')
            return
        self.log_step(f'Step 9: Found {len(unread_msgs["messages"])} new messages')
        for msg in unread_msgs['messages']:
            try:
                msg_raw = self.service.users().messages().get(userId='me', id=msg['id'], format="raw", metadataHeaders=None).execute()
                msg = message_from_bytes(base64.urlsafe_b64decode(msg_raw['raw']))
                msg_payload = msg.get_payload()
                msg_html = html.fromstring(msg_payload)
                confirm_link = msg_html.xpath('//a[contains(@href, "booking/confirm")]')
                confirm_url = confirm_link[0].attrib['href']
                self.log_step(f'Step 10: Following confirmation url: `{confirm_url}`')
                page = requests.get(confirm_url, headers=HttpClient.DEFAULT_HEADERS)
                if not page:
                    save_html(page.content)
                    raise Exception(f'☠️ Step 10: Url was not loaded. Status code: {page.status_code}')
                self.log_step(f'✅ Step 10: Confirmation page loaded `{confirm_url}`')
                tree = html.fromstring(page.content)
                confirm_form = tree.xpath("//*[@id='inner_Booking']/form")
                if not len(confirm_form):
                    save_html(page.content)
                    raise Exception('☠️ Confirmation form not found')
                confirm_url = f"{self.config.url}{confirm_form[0].attrib['action']}"
                confirm_btn = tree.xpath("//input[@name='createButton']")
                if not len(confirm_btn):
                    save_html(page.content)
                    raise Exception('☠️ Confirmation button not found')
                self.log_step(f'Step 11: Submitting confirmation to: `{confirm_url}`')
                page = requests.post(
                    confirm_url,
                    headers={**HttpClient.DEFAULT_HEADERS, 'referer': confirm_url, 'origin': confirm_url},
                    cookies=page.cookies,
                    data={'createButton': confirm_btn[0].value})
                save_html(page.content)
                if not page:
                    raise Exception(f'☠️ Step 11: Confirmation not submitted. Status code: {page.status_code}')
                self.log_step(f'✅ RDV fully confirmed!')
            except Exception as ex:
                self.log_step(f'☠️ Exception: {ex}')
                self.logger.exception(ex)
