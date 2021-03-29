# Book RDV in :fr: Prefectures 
Helper script in python to monitor dates availabilities in Prefectures and book appointments automatically

## Features
1. Monitoring RVD dates availability per week per appointment type
2. Support list of proxies that allows to avoid `502 Bad Gateway` server-side throttling (some cheap proxies available on [webshare.io](https://www.webshare.io/?referral_code=932pt9udqsmj)). 
3. Sending notification via [Telegram Bot](https://core.telegram.org/bots)
4. Automatic captcha validation using [anti-captcha.com](http://getcaptchasolution.com/6ycdl1mx0u)
5. Automatic appointment booking for multiple people in parallel.

To access most of these features you'll need to setup related infrastructure yourself, see the section below.

## Setup
The script currently requires python 3.6+ and tailored to run on local machine. To install all dependencies run:
```bash
$ pip install -r requirements.txt
```
### Proxies
Provide list of proxies to avoid receiving `502 Gateway` from prefecture website after several requests in short period. The script has no delay between attempts,
so it's firing requests as soon as possible (~1 second) making it pretty easy to reach. So it's *strongly recommend* either to add delay (~30 seconds) or add proxies.
100 :fr: proxies could be bought for ~3$ per month from [webshare.io](https://www.webshare.io/?referral_code=932pt9udqsmj) (referral link).
1. Put proxies in format `host:port` (one proxy per line) in `./proxies.txt`
2. Set `username` and `password` in `proxy_config` (`user_data.py`) or leave blank for non-restricted access

### Telegram notifications
Appointment dates often appear at random times and you won't be sitting in from of your computer, so it's having reactive notification system helps a lot.
To set up Telegram bot:
1. Create bot via `@BothFather` following these [instructions](https://core.telegram.org/bots#3-how-do-i-create-a-bot).
2. Update `telegram_bot_token` with HTTP API Key (retrieved in previous step) in `user_data.py`

### Captcha validation
Being able to walk away from the computer and have your appointment booked without extra intervention is priceless, while captchas could be easily solved by
3rd party providers, often faster than manually. [anti-captcha.com](http://getcaptchasolution.com/6ycdl1mx0u) (referral link) provides test credit for free, which is enough
to solve 20-40 reCAPTCHAv2.
To integrate using their script:
1. [Register](http://getcaptchasolution.com/6ycdl1mx0u)
2. Request free credit (~0.05$ per phone number) or [buy](https://anti-captcha.com/clients/finance/refill) sufficient credit directly (min 10$) or using one of the [resellers](https://anti-captcha.com/clients/finance/resellers/list) (smaller budget).
3. Update `anticaptcha_api_key` in `user_data.py` by HTTP API Key

### Appointment booking
Avoid typing personal data and unblock parallel booking for several users at a time by populating `form_data` in `user_data.py`.

### RVD configuration
You should have an appointment URL which looks like this:
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

### Run Locally
To start polling given prefecture website run from the local machine simply run:
```bash
$ python main.py [nb-attempts]
```
Last argument allows to specify how many time to run the check, which is useful for debugging (`python main.py 1`)

### Run docker container remotely
 1. Register on [Docker Hub](https://hub.docker.com/)
 2. Create an image (1 private image is available with free account)
 3. Setup any web-hook for Azure/Aws deployment
 4. Run:

```bash
docker image build -t <image name> .
docker push <image name>:<tag-name>
```