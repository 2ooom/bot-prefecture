
import requests
import json
import logging
import concurrent.futures
import threading

from utils import get_bin_file_content, get_json_file_content
from users_data import telegram_bot_token

class TelegramBot:
    DB_PATH = './bot_state.json'
    pass_phrase = set(['please', 'let', 'me', 'in'])

    def __init__(self):
        self.root_url = f'https://api.telegram.org/bot{telegram_bot_token}'
        self.db_path = TelegramBot.DB_PATH
        self.state = get_json_file_content(self.db_path)
        self.logger = logging.getLogger("Telegram Bot")

    def save_state(self):
        with open(self.db_path, "w") as f:
            f.write(json.dumps(self.state))

    def check_new_subscribions(self):
        last_update_id = self.state['last_update_id']
        subscribers_ids = set(self.state['subscribers_ids'])
        updates = requests.get(f'{self.root_url}/getUpdates?offset={last_update_id + 1}').json()
        for update in updates['result']:
            if update['update_id'] > last_update_id:
                last_update_id = update['update_id']
            msg = update['message']
            sender = msg['from']
            user_name = " ".join(list(map(lambda field: f"{field}: {sender[field]};" if field in sender else f"{field}: <empty>;", ['first_name', 'last_name', 'username'])))

            if set(msg['text'].strip().lower().split()) == TelegramBot.pass_phrase:
                chat_id = msg['chat']['id']
                subscribers_ids.add(chat_id)
                self.logger.info(f'Subscribing {user_name} [{chat_id}] to notifications')
            else:
                self.logger.info(f'Unknown message from {user_name}')
        self.state['subscribers_ids'] = list(subscribers_ids)
        self.state['last_update_id'] = last_update_id
        self.save_state()

    def send_all(self, message):
        self.logger.debug('Sending message to all subscriers...')
        try:
            for chat_id in self.state['subscribers_ids'][:1]:
                sending_thread = threading.Thread(target=self.send_single_message, args=(message, chat_id))
                sending_thread.start()
        except Exception as ex:
            self.logger.error(f'Error sending notification:')
            self.logger.exception(ex)


    def send_single_message(self, message, chat_id):
        # https://core.telegram.org/bots/api#available-methods
        self.logger.debug(f'[Chat {chat_id}]: Sending message...')
        response = requests.post(f'{self.root_url}/sendMessage', json={
            'chat_id' : chat_id,
            'parse_mode' : 'Markdown',
            'text': message
        })
        if not response.ok:
            self.logger.warning(f'[Chat {chat_id}]: Sendig message failed: `{response.json()}`')
        return response.json()

    def send_to_admins(self, message, file_path=None, file_type=None):
        self.logger.debug('Sending message to all admins...')
        try:
            if 'admin_ids' not in self.state:
                self.logger.error(f'No admins configured:')
                return
            chat_ids = self.state['admin_ids']
            if file_path:
                file_bytes = get_bin_file_content(file_path)
                send_method = self.send_single_photo if file_type == 'photo' else self.send_single_document
                for chat_id in chat_ids:
                    threading.Thread(target=send_method, args=(file_bytes, message, chat_id)).start()
            else:
                for chat_id in chat_ids:
                    threading.Thread(target=self.send_single_message, args=(message, chat_id)).start()
        except Exception as ex:
            self.logger.error(f'Error sending notification:')
            self.logger.exception(ex)

    def send_single_photo(self, photo_bytes, message, chat_id):
        self.logger.debug(f'[Chat {chat_id}]: Sending photo...')
        response = requests.post(f'{self.root_url}/sendPhoto?chat_id={chat_id}&caption={message}&parse_mode=Markdown', files={
            'photo': photo_bytes
        })
        if not response.ok:
            self.logger.warning(f'[Chat {chat_id}]: Sendig photo with message "{message}" failed: `{response.json()}`')
        return response.json()
    
    def send_single_document(self, document_bytes, message, chat_id):
        self.logger.debug(f'[Chat {chat_id}]: Sending document...')
        response = requests.post(f'{self.root_url}/sendDocument?chat_id={chat_id}&caption={message}&parse_mode=Markdown', files={
            'document': document_bytes
        })
        if not response.ok:
            self.logger.warning(f'[Chat {chat_id}]: Sendig document with message "{message}" failed: `{response.json()}`')
        return response.json()