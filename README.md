# Book RDV in :fr: Prefectures 
Helper script in python to monitor dates availabilities in Prefectures and book apointments automatically

## Features
1. Monitoring RVD dates availability per week per appointment type
2. Support list of proxies that allows to avoid `502 Bad Gateway` server-side throttling (some cheap proxies available on [webshare.io](https://www.webshare.io/?referral_code=932pt9udqsmj)). 
3. Sending notification via [Telegram Bot](https://core.telegram.org/bots)
4. Automatic captcha validation using [anti-captcha.com](http://getcaptchasolution.com/6ycdl1mx0u)
5. Automatic appointment booking for multiple people in parallel using [Selenium Python bindings](https://selenium-python.readthedocs.io/) over [Firefox Geckodriver](https://github.com/mozilla/geckodriver/releases)

To access most of these features you'll need to setup related infrastructure yourself, see the section below.

## Setup
The script currently requires python 3.6+ and tailored to run on local machine. To install all dependencies run:
```bash
$ pip install -r requirements.txt
```
### Proxies
Provide list of proxies to avoid receiving `502 Gateway` from prefecture website after several requests in shoort period. The script has no delay between attempts,
so it's firing requests as soon as possible (~1 second) making it pretty easy to reach. So it's *strongly recommend* either to add delay (~30 seconds) or add proxies.
100 :fr: proxies could be bought for ~3$ per month from [webshare.io](https://www.webshare.io/?referral_code=932pt9udqsmj) (referral link).
Once you have proxies list in format `host:port` (one proxy per line):
1. Put them in `./proxies.txt` file
2. Run script at least once for the entire list of proxies to populate `./proxies-working.txt`
3. Replace content of `./proxies.txt` with the content of `./proxies-working.txt` to avoid using fault proxies and speed up date detection

#### If you're webshare's proxies:
Script currently doesn't support password protected proxies, so make sure to explicitly allow external IP addresses pf your host in  the webshare's dashboard

### Telegram notificatons
Appointment dates often appear at random times and you won't be sitting in from of your computer, so it's having reactive notification system helps a lot.
To set up Telegram bot:
1. Create bot via `@BothFather` following theese [instructons](https://core.telegram.org/bots#3-how-do-i-create-a-bot).
2. Update `telegram_bot_token` with HTTP API Key (retrieved in previous step) in `user_data.py`

### Captcha validation
Beeing able to walk away from the computer and have your apporintment booked without extra intervention is priceless, while captchas could be easily solved by
3rd party providers, often faster than manually. [anti-captcha.com](http://getcaptchasolution.com/6ycdl1mx0u) (referral link) provides test credit for free, which is enough
to solve 20-40 reCAPTCHAv2.
To integrate using their script:
1. [Register](http://getcaptchasolution.com/6ycdl1mx0u)
2. Request free credit (~0.05$ per phone number) or [buy](https://anti-captcha.com/clients/finance/refill) sufficient credit directly (min 10$) or using one of the [resellers](https://anti-captcha.com/clients/finance/resellers/list) (smaller budget).
3. Update `anticaptcha_api_key` in `user_data.py` by HTTP API Key

### Appointment booking
Avoid typing personal data and unblock parallel booking for several users at a time by populating `form_data` in `user_data.py`.

### RVD configuration
You hsould have an appointment URL which looks like this:
```
https://www.seine-saint-denis.gouv.fr/booking/create/9846/0
```
And follow the steps manually *at least once*  to sniff some of the configuration from the Developer Tools, watching for the outgoing AJAX requests that looks like:
```
https://www.seine-saint-denis.gouv.fr/ezjscore/call/bookingserver::planning::assign::9846::{config.ajax_id}::{week}
```
To set up polling for this specific example you'll need update the following `Config` properties in `config.py`:
 * `url` - prefecture website (`https://www.seine-saint-denis.gouv.fr`)
 * `form_id` - RVD type (`9846`)
 * `ajax_id` - the subtype/giche of the RVD. Could be found when looking at the timetable screens with browser dev-tools
 * `week_first`, `week_last` - incremental identifier of the week for which you want to get RVD. These IDs very per prefecture and RVD type, same as `ajax_id`

### Run
To start polling given prefecture website run:
```bash
$ python main.py
```
