# Base Url
CONTRACT_WS_URL = 'wss://fx-api-testnet.gateio.ws/v4/ws'
# 测试环境为test，生产环境为prd
ENV = 'test'
API_URL = 'https://api.gateio.ws/api/v4' if ENV == 'prd' else 'https://fx-api-testnet.gateio.ws/api/v4'

PRODUCT_TYPE = 'USDT-FUTURES'

# http header
CONTENT_TYPE = 'Content-Type'
OK_ACCESS_KEY = 'ACCESS-KEY'
OK_ACCESS_SIGN = 'ACCESS-SIGN'
OK_ACCESS_TIMESTAMP = 'ACCESS-TIMESTAMP'
OK_ACCESS_PASSPHRASE = 'ACCESS-PASSPHRASE'
APPLICATION_JSON = 'application/json'

# header key
LOCALE = 'locale'

# method
GET = "GET"
POST = "POST"
DELETE = "DELETE"

# sign type
RSA = "RSA"
SHA256 = "SHA256"
SIGN_TYPE = SHA256

# ws
REQUEST_PATH = '/user/verify'

# ACCOUNT INFO
API_KEY = 'baffffe996db428683cc4c9ea945ad87'
API_SECRET = 'a9e3f7eb91f9b545ca8d690fe93a99fcb709445a68f21cbfd83fae91f4510288'
API_PASSPHRASE = 'robin3910'
IP_WHITE_LIST = ['52.89.214.238', '34.212.75.30', '54.218.53.128', '52.32.178.7', '127.0.0.1']

# 微信通知配置
WX_TOKEN = 'SCT264877TGGj20niEYBVMMFU1aN6NQF6g'
SETTLE = 'usdt'

# 策略配置
STRATEGY_CONFIG = {
    'funding_rate_limit': -0.3, # 单位%，例如资金费率要大于-0.3%，才能开仓
    'entry_limit_percent': 4, # 单位%，例如4小时K棒要下跌超过5%，才能开仓
    'entry_price_add_percent': 0, # 单位%，例如开仓价格要在当前价格的3%以上
    "entry_usdt_percent": 0.1, # 每次入仓占总资金的比例
    'sl_percent': 99, # 单位%，例如止损价格要在当前价格的20%以下
    'tp_percent': 10, # 单位%，例如止盈价格要在当前价格的10%以上
}

# 错误码
SUCCESS = "00000"
