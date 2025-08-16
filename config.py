# Binance API配置
env = 'test'
BINANCE_CONFIG = {
    'key': '6953af36dcec691ee0cb266cf60d13e58bcc3f9c8f9d71b8b899090e649e3898',
    'secret': '2e9d0e67d0585312bbefc7aa7e4dcbdb1d2991b8b7665a76c4c11b022bc88f91',
    'base_url': 'https://fapi.binance.com' if env == 'prod' else 'https://testnet.binancefuture.com',
    'ip_white_list': ['52.89.214.238', '34.212.75.30', '54.218.53.128', '52.32.178.7', '127.0.0.1']
}

# 微信通知配置
WX_CONFIG = {
    'token_list': ['SCT264877TGGj20niEYBVMMFU1aN6NQF6g','SCT268240TBcMk5tPRtDwwFOdOkspgYmGl']
}

STRATEGY_CONFIG = {
    'funding_rate_limit': -0.3, # 单位%，例如资金费率要大于-0.3%，才能开仓
    'entry_limit_percent': 4, # 单位%，例如4小时K棒要下跌超过5%，才能开仓
    'entry_price_add_percent': 0, # 单位%，例如开仓价格要在当前价格的3%以上
    "entry_usdt_percent": 0.1, # 每次入仓占总资金的比例
    'sl_percent': 99, # 单位%，例如止损价格要在当前价格的20%以下
    'tp_percent': 10, # 单位%，例如止盈价格要在当前价格的10%以上
}

