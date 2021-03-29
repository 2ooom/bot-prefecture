from collections import namedtuple
Config = namedtuple('Config', ['url', 'form_id', 'ajax_id', 'week_first', 'week_last', 'recatcha_sitekey'])

config_hs = Config(
    url = 'https://www.hauts-de-seine.gouv.fr',
    form_id = 13525,
    ajax_id = 14202,
    week_first = 182, # 19-25 avril
    week_last = 190, # 26 avril - 02 mai
    recatcha_sitekey = '6LcIY58UAAAAAFhtNq8BzG8mriWbWtafuI3WhIL7',
)

config_sd = Config(
    url = 'https://www.seine-saint-denis.gouv.fr',
    form_id = 9846,
    ajax_id = 17637,
    week_first = 14,
    week_last = 44,
    recatcha_sitekey = '6Le_vJIUAAAAAF_nxFeSzwMYXsLoF4GJJIzF4tG1',
)

config = config_hs