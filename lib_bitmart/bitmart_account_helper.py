import datetime
import json
import os.path
import time
import traceback

import requests
from flask import request

from lib_bitmart.bitmart_account import BM_SUCCESS
from lib_bitmart.bitmart_account import BitMartAccount
# from sqlite_helper import SQliteHelper

class BitmartAccountHelper:
    def __init__(self, root_path="",logger=None):
        # 初始化日志
        self.logger=logger
        # 初始化应用路径
        self.root_path = root_path
        # 按照key索引存放账户信息
        self.accounts = []
        self.logger.debug("初始化bitmart AccountHelper")

        # 初始化配置文件中所有的账户
        self.init_accounts()
        #配置文件
        self.config = self.get_config()
    pass

    def init_accounts(self):
        self.logger.info("开始加载所有账户信息")
        # 加载json
        config_path = os.path.join(self.root_path, "lib_bitmart", "account_conifg.json")
        with open(config_path, 'r') as f:
            config = json.load(f)
            for account in config['account_list']:
                account_info = {
                    "api_key": account['api_key'],
                    "instance": BitMartAccount(api_key=account['api_key'], api_secret=account['secret_key'],
                                           memo=account['memo'], logger=self.logger)
                }
                # 实例化账户类
                self.accounts.append(account_info)
                self.logger.info(f"初始化账户: {account['api_key']}")
                pass


    # 根据api_key获取账户实例
    def get_account_info(self, api_key):
        for account in self.accounts:
            if account['api_key'] == api_key:
                return account['instance']
        pass

    # 加载全局配置文件
    def get_config(self):
        try:
            config_path = os.path.join(self.root_path, "lib_bitmart", "account_conifg.json")
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config
        except Exception as e:
            self.logger.error(f"读取配置文件出错: {str(e)}")
            return None

    def send_wx_notification(self, title, message):
        """
        发送微信通知
        Args:
            title: 通知标题
            message: 通知内容
        """
        try:
            requests.get(f'https://sctapi.ftqq.com/{self.config["global"]["wx_token"]}.send?text={title}&desp={message}')
            self.logger.info('发送微信消息成功')
        except Exception as e:
            self.logger.error(f'发送微信消息失败: {str(e)}')

    def prefix_symbol(self,s: str) -> str:
        # BINANCE:BTCUSDT.P -> BTC-USDT-SWAP
        # 首先处理冒号，如果存在则取后面的部分
        if ':' in s:
            s = s.split(':')[1]

        # 检查字符串是否以".P"结尾并移除
        if s.endswith('.P'):
            s = s[:-2]

        # 将 BTCUSDT 格式转换为 BTC-USDT-SWAP 格式
        if 'USDT' in s:
            base = s.replace('USDT', '')
            return f"{base}-USDT-SWAP"

        return s

    def monitor_new_coin(self, symbol, instance: BitMartAccount):
        """监控新币上线及交易条件"""
        self.logger.info(f"bitmart开始监控新币: {instance.api_key}")
        
        # 获取公共数据API
        tradeAPI = instance.get_trade_api()
        symbol_exists = False
        tick_size = 0
        while True:
            try:
                if symbol_exists == False:
                    instruments = tradeAPI.get_details(contract_symbol=symbol)[0]
                
                    # 获取所有可交易的合约信息
                    
                    if instruments['code'] == BM_SUCCESS:
                        # 检查合约是否存在
                        for instrument in instruments['data']['symbols']:
                            if instrument['symbol'] == symbol:
                                symbol_exists = True
                                # 获取合约的精度信息
                                tick_size = instrument['price_precision']
                                self.logger.info(f"合约精度信息: tick_size={tick_size}")
                                self.logger.info(f"bitmart-{symbol} 合约已上线")
                                break
                    
                if symbol_exists:
                    # 获取4小时K线数据
                    end_time = int(time.time())
                    start_time = end_time - 3 * 240 * 60  # 3根4小时K线
                    klines = tradeAPI.get_kline(
                        contract_symbol=symbol,
                        step=240,
                        start_time=start_time,
                        end_time=end_time
                    )[0]
                    self.logger.info(klines)
                    
                    # 0是最早的一根
                    # 1是中间的
                    # 2是当前的
                    if klines['code'] == BM_SUCCESS and len(klines['data']) >= 3:
                        # 计算前两根K线的跌幅
                        prev_open = float(klines['data'][1]['open_price'])    # 倒数第二根K线开盘价
                        prev_close = float(klines['data'][1]['close_price'])   # 倒数第二根K线收盘价
                        
                        prev_prev_open = float(klines['data'][0]['open_price'])    # 倒数第三根K线开盘价
                        prev_prev_close = float(klines['data'][0]['close_price'])   # 倒数第三根K线收盘价
                        
                        # 获取资金费率
                        funding_rate_info = tradeAPI.get_funding_rate(symbol)[0]
                        funding_rate = float(funding_rate_info['data']['rate_value'])
                        
                        # 获取标记价格
                        mark_price_info = tradeAPI.get_details(contract_symbol=symbol)[0]
                        mark_price = float(mark_price_info['data']['symbols'][0]['index_price'])
                        
                        funding_rate_limit = float(self.config["STRATEGY_CONFIG"]['funding_rate_limit']) / 100
                        # 判断是否满足做空条件
                        is_bearish = (prev_close < prev_open and 
                                    prev_prev_close < prev_prev_open and 
                                    funding_rate > funding_rate_limit)  # 资金费率大于1%
                        # if is_bearish:
                        if True:
                            try:
                                # 获取账户余额
                                balance = instance.get_balance()
                                
                                entry_usdt_percent = float(self.config["STRATEGY_CONFIG"]['entry_usdt_percent'])
                                # 计算入场金额（使用账户余额的一半）
                                entry_usdt = balance * entry_usdt_percent
                                
                                # 计算入场价格（当前标记价格上浮0.1%）
                                price_precise = instance.get_decimal_places(tick_size=tick_size)
                                entry_price = round(mark_price * 1.001, price_precise)

                                # 使用instance的amount函数计算下单数量
                                quantity = instance.amountConvertToSZ(symbol, entry_usdt / entry_price)
                                
                                # 计算下单数量
                                self.logger.info(f"{symbol}做空入场: 账户余额:{balance}|"
                                                f"入场金额:{entry_usdt}|入场价格:{entry_price}|"
                                                f"数量:{quantity}")
                                
                                order_result = tradeAPI.post_submit_order(
                                    contract_symbol=symbol,
                                    side=4, # 做空
                                    type="limit",
                                    leverage="10",
                                    open_type="cross",
                                    size=quantity,
                                    price=str(entry_price)
                                )[0]
                                self.logger.info(order_result)
                                
                                if order_result['code'] == BM_SUCCESS:
                                    order_id = order_result['data']['order_id']
                                    self.logger.info(f"开空单成功，订单ID: {order_id}")
                                    
                                    # 发送通知
                                    msg = f"bitmart-{symbol} 开空成功:\n" \
                                            f"价格: {mark_price}\n" \
                                            f"数量: {quantity}\n" \
                                            f"订单ID: {order_id}"
                                    self.send_wx_notification(f"bitmart-{symbol}", msg)
                                    
                                    # 开仓成功后退出循环
                                    self.logger.info(f"{symbol} 开仓成功，退出监控循环")
                                    return True
                                    
                                else:
                                    self.logger.error(f"开空单失败: {order_result}")
                                    self.send_wx_notification("新币监控", 
                                                            f"{symbol} 开空单失败: {order_result}")
                                    
                            except Exception as e:
                                error_msg = f"开空单异常: {str(e)}"
                                self.logger.error(error_msg)
                                self.send_wx_notification("新币监控", error_msg)
                
            except Exception as e:
                self.logger.error(f"监控新币异常: {str(e)}")
            
            time.sleep(60)  # 每分钟检查一次

# if __name__ == '__main__':
#     # 日志处理
#     root_path='E:\\project-2025\\tv_alert_bot_for_okex'
#     logger = get_logger(log_path_dir=root_path)
#     helper=OkxAccountHelper(root_path,logger)
#     for account in helper.accounts:
#         c = helper.load_symbol_info(account['instance'])
#         helper.save_symbol_info(c,account['instance'])
#
#     pass