form_data = {
    'email': 'xxxx@gmail.com',
    'emailcheck': 'xxxx@gmail.com',
    'firstname': 'Xxx',
    'lastname': 'Xxxx',
    'number_agdref': '1234567890',
    'end_date_validity': 'dd/mm/yyyy',
    'post_code': 'xxxxx',
}

anticaptcha_api_key = 'xxx'

telegram_bot_token = 'xxx'

ProxyConfig = namedtuple('ProxyConfig', ['username', 'password'])
proxy_config = ProxyConfig(
    username='xxx',
    password='xxx'
)

AzureInsights = namedtuple('AzureInsights', ['connection_string', 'instrumentation_key'])
azure_insights = AzureInsights(
    connection_string='InstrumentationKey=xxx;IngestionEndpoint=https://francecentral-0.in.applicationinsights.azure.com/',
    instrumentation_key='xxx'
)