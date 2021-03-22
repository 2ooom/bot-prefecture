from collections import namedtuple
Config = namedtuple('Config', ['url', 'form_id', 'ajax_id', 'week_first', 'week_last'])

config_hs = Config(
    url = 'https://www.hauts-de-seine.gouv.fr',
    form_id = 13525,
    ajax_id = 14202,
    week_first = 182, # 19-25 avril
    week_last = 183 # 19-25 avril
)

config_sd = Config(
    url = 'https://www.seine-saint-denis.gouv.fr',
    form_id = 9846,
    ajax_id = 17637,
    week_first = 14,
    week_last = 15
)

config = config_hs