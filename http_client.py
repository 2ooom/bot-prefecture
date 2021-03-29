import logging
import requests
import random
import time

from requests.exceptions import ReadTimeout, ProxyError
from collections import deque
from users_data import proxy_config
from utils import save_html

class HttpClient:
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:86.0) Gecko/20100101 Firefox/86.0"
    REQ_TIMEOUT = 7

    def __init__(self, proxies_path):
        self.logger = logging.getLogger("Http")
        self.proxies_path = proxies_path
        self.proxies = self.get_proxies(proxies_path)
        self.proxies_queue = deque(sorted(self.proxies, key=lambda _: random.random()))

    def get_proxies(self, proxies_path):
        proxies = set()
        with open(proxies_path, "r") as f:
            while True:
                line = f.readline()
                if not line:
                    break
                proxies.add(line.strip())
        self.logger.info(f"{len(proxies)} proxies loaded")
        return proxies

    def get_next_proxy_url(self):
        proxy_endpoint = self.proxies_queue.pop()
        self.proxies_queue.appendleft(proxy_endpoint)
        self.logger.debug(f'Using proxy {proxy_endpoint}')
        if proxy_config.username and proxy_config.password:
            return f"http://{proxy_config.username}:{proxy_config.password}@{proxy_endpoint}"
        else:
            return f"http://{proxy_endpoint}"

    def get(self, url, max_retries=1, cookies=None, headers={}, data=None):
        return self.req('get', url, max_retries, cookies=cookies, headers=headers, data=data)

    def req(self, method, url, max_retries=1, cookies=None, headers={}, data=None):
        proxy_url = self.get_next_proxy_url()

        last_response = None

        for attempt in range(0, max_retries):
            attempt_text = f'Attempt {attempt + 1}:'
            try:
                last_response = requests.request(
                    method,
                    url,
                    cookies=cookies,
                    headers={
                        **headers,
                        "user-agent": HttpClient.USER_AGENT,
                    },
                    data=data,
                    timeout=HttpClient.REQ_TIMEOUT,
                    proxies={'http': proxy_url, 'https': proxy_url}
                )
                if not last_response.ok:
                    self.logger.warning(f"{attempt_text} Failed with status code {last_response.status_code}")
                    if last_response.status_code == 403:
                        # delisting faulty proxy
                        self.logger.warning(f"{attempt_text} Delisting faulty proxy {proxy_url}")
                        self.proxies_queue.popleft()
                        self.proxies.remove(proxy_url)
                        with open(self.proxies_path, 'w') as f:
                            f.writelines(list(self.proxies))
                    elif last_response.status_code == 502:
                        self.logger.warning(f"{attempt_text} 502 - Bad Gateway")
                        time.sleep(3)
                    else:
                        save_html(date_table.content)
                    if attempt < max_retries - 1:
                        # setting new proxy
                        proxy_url = self.get_next_proxy_url()
                else:
                    return last_response
            except Exception as ex:
                if type(ex) in [ReadTimeout, ProxyError]:
                    self.logger.warning(f'{attempt_text} Timeout')
                else:
                    self.logger.warning(f"{attempt_text}: Failed with exception:")
                    self.logger.exception(ex)
                time.sleep(attempt + 1)
        return last_response


    def check_once(proxy_endpoint, week, logger, browsers):
        proxy_url = f"http://{proxy_config.username}:{proxy_config.password}@{proxy_endpoint}"
        try:
            date_table = requests.get(
                f"{config.url}/ezjscore/call/bookingserver::planning::assign::{config.form_id}::{config.ajax_id}::{week}",
                timeout=REQ_TIMEOUT,
                headers={"user-agent": user_agent},
                proxies={'http': proxy_url, 'https': proxy_url}
            )
        except ReadTimeout as timeout_ex:
            logger.warning('Timeout...')
            return
        except ProxyError as proxy_timeout_ex:
            logger.warning('Proxy side timeout...')
            return