import time
import os
import logging
import json

from datetime import datetime as dt

SESSION_ID_COOKIE = 'eZSESSID'
DUMPS_FOLDER = './dumps'

def get_file_content(filepath):
    with open(filepath, "r") as f:
        return f.read()

def get_json_file_content(filepath):
    with open(filepath, "r") as f:
        return json.load(f)

def get_bin_file_content(filepath):
    with open(filepath, "rb") as f:
        return f.read()

def with_retry(fn, max_retry, logger, *fn_args, **fn_kwargs):
    ex_to_raise = None
    for attempt in range(0, max_retry):
        try:
            return fn(*fn_args, **fn_kwargs)
        except Exception as ex:
            logger.warning(f"Attempt {attempt + 1} failed. Trying again")
            logger.exception(ex)
            ex_to_raise = ex
            time.sleep(attempt + 1)

    logger.error(f"All attempts ({max_retry}) failed. raising exception")
    raise ex_to_raise


def save_html(html, name=None):
    filename = name if name else dt.now().isoformat()
    html_path = os.path.abspath(
        os.path.join(DUMPS_FOLDER, f'{filename}.html')
    )
    with open(html_path, 'wb') as f:
        f.write(html)
    return html_path

def setup_logging(filepath):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)-5.5s] [%(name)s] %(message)s', "%H:%M:%S")

    fh = logging.FileHandler(filepath, mode='a')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    root_logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)
    root_logger.addHandler(ch)