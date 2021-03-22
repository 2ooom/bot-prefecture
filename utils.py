import time

user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.16; rv:86.0) Gecko/20100101 Firefox/86.0"

def get_file_content(filepath):
    with open(filepath, "r") as f:
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