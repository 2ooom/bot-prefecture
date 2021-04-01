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

    def __init__(self, store, emails, config):
        self.store = store
        self.checkers = {}
        self.emails = emails
        self.config = config

    def start_loop(self):
        for email in self.emails:
            email_check_thread = threading.Thread(target=self.loop, args=(email,), daemon=True)
            self.checkers[email] = email_check_thread
            email_check_thread.start()

    def loop(self, email):
        logger = logging.getLogger(f"MailChecker {email}")
        logger.info('Fetching and validating credentials')
        credentials = self.store.get_credentials(email)
        service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials)
        logger.info(f'Credentials validated. Starting to regular check:')
        while True:
            try:
                self.check_once(email, service, logger)
            except Exception as ex:
                logger.error('Checking failed. Error:')
                logger.exception(ex)
            time.sleep(MailChecker.DELAY_IN_SECONDS)

    def check_once(self, email, service, logger):
        unread_msgs = service.users().messages().list(userId='me', labelIds=['UNREAD', 'INBOX'], q='subject:"Demande de rendez-vous en attente de confirmation"').execute()
        if unread_msgs['resultSizeEstimate'] <= 0:
            logger.info('No new messages')
            return
        logger.info(f'✉️ Found {len(unread_msgs["messages"])} new messages')
        for msg in unread_msgs['messages']:
            msg_raw = service.users().messages().get(userId='me', id=msg['id'], format="raw", metadataHeaders=None).execute()
            msg = message_from_bytes(base64.urlsafe_b64decode(msg_raw['raw']))
            msg_payload = msg.get_payload()
            msg_html = html.fromstring(msg_payload)
            confirm_link = msg_html.xpath('//a[contains(@href, "booking/confirm")]')
            confirm_url = confirm_link[0].attrib['href']
            logger.warning(f'Step 10: Following confirmation url: {confirm_url}')
            default_headers = {'user-agent': HttpClient.USER_AGENT}
            page = requests.get(confirm_url, headers= default_headers)
            if not page:
                save_html(page.content)
                raise Exception(f'☠️ Step 10: Url was not loaded. Status code: {page.status_code}')
            logger.warning(f'✅ Confirmation page loaded {confirm_url}')
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
            logger.warning(f'Step 11: Submitting confirmation to: {confirm_url}')
            page = requests.post(
                confirm_url,
                headers={**default_headers, 'referer': confirm_url, 'origin': confirm_url},
                cookies=page.cookies,
                data={confirm_btn[0].value})
            save_html(page.content)
            if not page:
                raise Exception(f'☠️ Step 11: Confirmation not submitted. Status code: {page.status_code}')
            logger.warning(f'✅ RDV confirmed!')
