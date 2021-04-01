import logging
import sys
import os
import json
import threading

from watcher import Watcher
from browser import Browser
from telegram_bot import TelegramBot
from http_client import HttpClient
from users_data import form_data, anticaptcha_api_key, telegram_bot_token, proxy_config, azure_insights

from config import config

from main import DB_PATH, PROXIES_PATH
from utils import DUMPS_FOLDER
from datetime import datetime as dt
from metrics import Metrics
from credentials_store import CredentialsStore
from mail_checker import MailChecker

from opencensus.ext.azure.log_exporter import AzureLogHandler

from flask import jsonify
from flask import request
from flask import Flask, escape, request
from flask import render_template

from google_auth_oauthlib.flow import Flow

GMAIL_READONLY_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
OAUTH2_CLIENT_SECRET_PATH = './google_client_secret.json'
OATH2_CREDENTIALS_STORE = './credentials.json'

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)-5.5s] [%(name)s] %(message)s', "%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)
    root_logger.addHandler(ch)

    az = AzureLogHandler(connection_string=azure_insights.connection_string)
    az.setLevel(logging.INFO)
    root_logger.addHandler(az)


setup_logging()

app = Flask(__name__)

logger = logging.getLogger("Server")

if not os.path.exists(DUMPS_FOLDER):
    os.makedirs(DUMPS_FOLDER)

service_started = dt.now()
tg_bot = TelegramBot(telegram_bot_token, DB_PATH)
http_client = HttpClient(PROXIES_PATH)
store = CredentialsStore(OAUTH2_CLIENT_SECRET_PATH, OATH2_CREDENTIALS_STORE)

browsers = []
emails = []
for data in form_data:
    br = Browser(config, data, tg_bot, http_client)
    emails.append(data['email'])
    browsers.append(br)

mail_checker = MailChecker(store, emails, config)
mail_checker_thread = threading.Thread(target=mail_checker.start_loop, daemon=True)
mail_checker_thread.start()
logger.info("Started checking emails")

metrics = Metrics(export_metrics=True)
watcher = Watcher(tg_bot, http_client, browsers[0].url_start, browsers, metrics, use_say_cmd=False)
watcher_thread = threading.Thread(target=watcher.start_loop, args=(None, 1), daemon=True)
watcher_thread.start()
logger.info("Started watching for dates")

@app.route('/')
def index():
    avg_req_time = watcher.global_time_counter/watcher.global_req_counter if watcher.global_req_counter else 0
    metrics = [
        f"Nb. requests: {watcher.global_req_counter}",
        f"Average request time: {'{:.2f}'.format(avg_req_time)} s",
        f"Service uptime: {(dt.now() - service_started)}"
    ]

    return render_template(
        'index.html',
        metrics=metrics,
        client_id=store.oauth_secrets['client_id'],
        scope=GMAIL_READONLY_SCOPE
    )


@app.route('/store_authcode', methods=['POST'])
def store_authcode():
    # If this request does not have `X-Requested-With` header, this could be a CSRF
    if not request.headers.get('X-Requested-With'):
        abort(403)
    flow = Flow.from_client_secrets_file(
        OAUTH2_CLIENT_SECRET_PATH,
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            GMAIL_READONLY_SCOPE,
        ],
        redirect_uri='postmessage')

    flow.fetch_token(code=request.data)
    email = store.update_credentials(flow.credentials)
    return jsonify({'email': email})