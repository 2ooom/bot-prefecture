from collections import namedtuple
Config = namedtuple('Config', ['url', 'form_id', 'week_first', 'week_last', 'recapcha_sitekey'])

HAUTS_DE_SEINE_CONFIG = Config(
        url = 'https://www.hauts-de-seine.gouv.fr',
        form_id = 13525,
        week_first = 175, # 11-18 avril
        week_last = 181,
        recapcha_sitekey = '6LcIY58UAAAAAFhtNq8BzG8mriWbWtafuI3WhIL7',
    )
HAUTS_DE_SEINE_BIOMETRY_CONFIG = Config(
        url = 'https://www.hauts-de-seine.gouv.fr',
        form_id = 11681,
        week_first = -1,
        week_last = -1,
        recapcha_sitekey = '6LcIY58UAAAAAFhtNq8BzG8mriWbWtafuI3WhIL7',
    )
configs = {
    'hauts-de-seine' : HAUTS_DE_SEINE_CONFIG,
    'hauts-de-seine-bio' : HAUTS_DE_SEINE_BIOMETRY_CONFIG,
    'saint-denis': Config(
        url = 'https://www.seine-saint-denis.gouv.fr',
        form_id = 9846,
        week_first = 28,
        week_last = 34,
        recapcha_sitekey = '6Le_vJIUAAAAAF_nxFeSzwMYXsLoF4GJJIzF4tG1',
    ),
}