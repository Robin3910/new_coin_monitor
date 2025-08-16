# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from functools import wraps
import requests
import logging
from logging.handlers import RotatingFileHandler
import lib_gateio.gate_config as CONFIG
from decimal import Decimal as D, ROUND_UP, getcontext
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder, FuturesPriceTriggeredOrder,FuturesPriceTrigger,FuturesInitialOrder, Transfer, WalletApi
from gate_api.exceptions import GateApiException
import time
import json
from config import WX_CONFIG

# app = Flask(__name__)

# 创建全局字典来存储不同币种的交易信息
trading_pairs = {}

# 配置信息
WX_TOKEN = CONFIG.WX_TOKEN
PRODUCT_TYPE = CONFIG.PRODUCT_TYPE
SETTLE = CONFIG.SETTLE
# 策略配置
STRATEGY_CONFIG = CONFIG.STRATEGY_CONFIG

symbol_tick_size = {} # 币种精度

# api_key = ""
# api_secret = ""

# 配置日志
def setup_logger():
    logger = logging.getLogger('gate_bot')
    logger.setLevel(logging.INFO)
    
    # 创建 rotating file handler，最大文件大小为 10MB，保留 5 个备份文件
    handler = RotatingFileHandler('gate_bot.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    return logger

class GateBot:
    def __init__(self, root_path="",logger=None):
        self.logger = setup_logger()
        self.logger.debug("初始化gateBot")
        self.logger.info(f"API_KEY: {CONFIG.API_KEY}")
        self.logger.info(f"API_SECRET: {CONFIG.API_SECRET}")
        self.client_gate_config = Configuration(key=CONFIG.API_KEY, secret=CONFIG.API_SECRET, host=CONFIG.API_URL)
        self.futures_api = FuturesApi(ApiClient(self.client_gate_config))

        exchange_info = self.futures_api.list_futures_contracts(SETTLE)
        for item in exchange_info:
            symbol_tick_size[item.name] = {
                'tick_size': len(str(float(item.order_price_round)).split('.')[-1].rstrip('0')),
                'min_qty': len(str(float(item.order_size_min)).split('.')[-1].rstrip('0')),
                "qty_to_contract": float(item.quanto_multiplier),
                "order_price_round": float(item.order_price_round)
            }

            # if item.name == "BNB_USDT":
            #     print(item)
            #     print(symbol_tick_size[item.name])
        acc = self.get_account()
        if acc != None:
            self.logger.info(f"账户余额信息: {json.dumps(acc.to_dict(), ensure_ascii=False, indent=2)}")
            self.logger.debug("初始化gateBot成功")

    def get_account(self):
        try:
            res = self.futures_api.list_futures_accounts(SETTLE)
            return res
        except GateApiException as ex:
            print("error %s", ex)
            return None

    # 对币种信息预处理
    def prefix_symbol(self, s: str) -> str:
        # BINANCE:BTCUSDT.P -> BTC_USDT
        # 首先处理冒号，如果存在则取后面的部分
        if ':' in s:
            s = s.split(':')[1]
        
        # 检查字符串是否以".P"结尾并移除
        if s.endswith('.P'):
            s = s[:-2]

        # 将BTCUSDT转成BTC_USDT
        s = s.replace('USDT', '_USDT')

        return s

    def send_wx_notification(self, title, message):
        """
        发送微信通知
        
        Args:
            title: 通知标题
            message: 通知内容
        """
        try:
            mydata = {
                'title': title,
                'desp': message
            }
            # 遍历所有配置的token发送通知
            for token in WX_CONFIG['token_list']:
                requests.post(f'https://sctapi.ftqq.com/{token}.send', data=mydata)
            self.logger.info('发送微信消息成功')
        except Exception as e:
            self.logger.error(f'发送微信消息失败: {str(e)}')

    def get_decimal_places(tick_size):
        tick_str = str(float(tick_size))
        if '.' in tick_str:
            return len(tick_str.split('.')[-1].rstrip('0'))
        return 0

    def place_order(self, symbol, side, qty, price, order_type="limit", reduce_only=False):
        """下单"""
        # 带price就是委托单，不带price是市价单
        if order_type == "limit":
            tif = "gtc"
        else:
            tif = "ioc"
            price = 0
        

        if side == "sell":
            qty = -qty
            
        order = FuturesOrder(contract=symbol, size=qty, price=price, tif=tif, reduce_only=reduce_only)
        try:
            order_response = self.futures_api.create_futures_order(SETTLE, order)
            self.logger.info(f"order {order_response.id} created with status: {order_response.status}")
            return str(order_response.id)
        except GateApiException as ex:
            self.logger.error(f"error encountered creating futures order: {ex}")
            self.send_wx_notification(f"{symbol}|下单失败", f"下单失败: {ex}")
            return


    def cancel_price_trigger_order(self, symbol):
        """取消价格触发单"""
        try:
            order_response = self.futures_api.cancel_price_triggered_order_list(SETTLE, contract=symbol)
            return order_response
        except GateApiException as ex:
            self.logger.error(f"error encountered canceling price trigger order: {ex}")
            self.send_wx_notification(f"{symbol}|取消价格触发单失败", f"取消价格触发单失败: {ex}")

    def place_price_trigger_order(self, symbol, side, qty, price, order_type="limit", rule=1, reduce_only=False):
        """下单"""
        order_price = str(price)
        trigger_price = str(price)
        if order_type == "limit":
            tif = "gtc"
        else:
            tif = "ioc"
            order_price = "0"
        

        if side == "sell":
            qty = -qty
        
        # rule 1 代表价格 >= 触发价时触发， 2 代表价格 <= 触发价时触发
        initial_order = FuturesInitialOrder(contract=symbol, size=qty, price=order_price, tif=tif, reduce_only=reduce_only)
        trigger_order = FuturesPriceTrigger(strategy_type=0, price_type=0, price=trigger_price, rule=rule)
        order = FuturesPriceTriggeredOrder(initial=initial_order, trigger=trigger_order)
        try:
            order_response = self.futures_api.create_price_triggered_order(SETTLE, order)
            return str(order_response.id)
        except GateApiException as ex:
            self.logger.error(f"error encountered creating futures order: {ex}")
            self.send_wx_notification(f"{symbol}|挂单失败", f"挂单失败: {ex}")
            return

    def query_order(self, symbol, order_id):
        """查询订单"""
        try:
            order_response = self.futures_api.get_futures_order(SETTLE, order_id)
            return order_response
        except GateApiException as ex:
            self.logger.error(f'{symbol}|查询订单失败，错误: {ex}')
            return None

    def close_position(self, symbol):
        """市价平仓"""
        order = FuturesOrder(contract=symbol, size="0", close="true", price="0", tif="ioc")
        try:
            order_response = self.futures_api.create_futures_order(SETTLE, order)
            return order_response.id
        except GateApiException as ex:
            if ex.label == "POSITION_EMPTY":
                return None
            else:
                self.logger.error(f'{symbol}|平仓失败，错误: {ex}')
                self.send_wx_notification(f"{symbol}|平仓失败", f"平仓失败: {ex}")
                return None

    def get_position(self, symbol):
        """获取仓位"""
        position_size = 0
        try:
            position = self.futures_api.get_position(SETTLE, symbol)
            position_size = position.size
            return position_size
        except GateApiException as ex:
            self.logger.error(f'{symbol}|获取仓位失败，错误: {ex}')
            return 0

    def batch_place_order(self, symbol, order_list, reduce_only=False):
        """批量下单"""
        try:
            place_order_list = []
            for order in order_list:
                qty = order['size']
                tif = "gtc"
                price = order['price']
                # 带price就是委托单，不带price是市价单
                if order['orderType'] == "limit":
                    tif = "gtc"
                else:
                    tif = "ioc"
                    price = 0
                
                if order['side'] == "sell":
                    qty = -qty
                    
                order = FuturesOrder(contract=symbol, size=qty, price=price, tif=tif, reduce_only=reduce_only)
                place_order_list.append(order)
            order_response = self.futures_api.create_batch_futures_order(SETTLE, place_order_list)
            return order_response
        except GateApiException as ex:
            self.logger.error(f'{symbol}|批量下单失败，错误: {ex}')
            self.send_wx_notification(f"{symbol}|批量下单失败", f"批量下单失败: {ex}")
            return None

    def get_pending_orders(self,symbol):
        """获取挂单信息"""
        try:
            order_list = self.futures_api.list_futures_orders(SETTLE, status="open", contract=symbol)
            return order_list
        except GateApiException as ex:
            self.logger.error(f'{symbol}|获取挂单信息失败，错误: {ex}')
            return None

    def cancel_order(self,symbol, order_id):
        """取消指定ID的挂单"""
        try:
            order_response = self.futures_api.cancel_futures_order(SETTLE, order_id)
            self.logger.info(f'{symbol}|取消挂单成功: {order_response}')
        except GateApiException as ex:
            self.logger.error(f'{symbol}|取消挂单失败，错误: {ex}')
            self.send_wx_notification(f"{symbol}|取消挂单失败", f"取消挂单失败: {ex}")

    def cancel_all_orders(self, symbol):
        """取消该品种所有的挂单"""
        try:
            pending_orders = self.futures_api.list_futures_orders(SETTLE, status="open", contract=symbol)
            if pending_orders:
                order_id_list = [str(order.id) for order in pending_orders]
                order_response = self.futures_api.cancel_batch_future_orders(SETTLE, order_id_list)
                self.logger.info(f'{symbol}|取消挂单成功: {order_response}')
            else:
                self.logger.info(f'{symbol}|没有挂单')

            # 取消价格触发单
            self.cancel_price_trigger_order(symbol)
        except GateApiException as ex:
            self.logger.error(f'{symbol}|取消挂单失败，错误: {ex}')
            self.send_wx_notification(f"{symbol}|取消所有挂单失败", f"取消挂单失败: {ex}")

    def set_leverage(self, symbol, leverage):
        """设置杠杆"""
        try:
            self.futures_api.update_position_leverage(SETTLE, symbol, leverage=0, cross_leverage_limit=leverage)
        except GateApiException as ex:
            self.logger.error(f'{symbol}|设置杠杆失败，错误: {ex}')
            return None

    def set_position_mode(self, is_dual_mode):
        """设置持仓模式"""
        # is_dual_mode 为True表示双向持仓，为False表示单向持仓
        try:
            dual_mode_response = self.futures_api.set_dual_mode(SETTLE, is_dual_mode)
            return dual_mode_response
        except GateApiException as ex:
            self.logger.error(f'设置持仓模式失败，错误: {ex}')
            return None

    def batch_cancel_orders(self, symbol, order_id_list):
        """批量撤销指定ID的挂单"""
        try:
            order_response = self.futures_api.cancel_batch_future_orders(SETTLE, order_id_list)
            return order_response
        except GateApiException as ex:
            self.logger.error(f'{symbol}|批量撤销挂单失败，错误: {ex}')
            self.send_wx_notification(f"{symbol}|批量撤销挂单失败", f"批量撤销挂单失败: {ex}")
            return None

    def get_single_contract(self, symbol):
        """获取单个合约信息"""
        try:
            order_response = self.futures_api.get_futures_contract(SETTLE, symbol)
            return order_response
        except GateApiException as ex:
            self.logger.error(f'{symbol}|获取单个合约信息失败，错误: {ex}')
            return None
    
    def get_mark_price(self, symbol):
        """获取标记价格"""
        try:
            order_response = self.futures_api.get_futures_contract(SETTLE, symbol)
            return float(order_response.mark_price)
        except GateApiException as ex:
            self.logger.error(f'{symbol}|获取标记价格失败，错误: {ex}')
            return None

    # 设置持仓模式
    # set_position_mode(False)

    # 获取币种的精度
    def get_symbol_tick_size(self):
        try:
            global symbol_tick_size
            exchange_info = self.futures_api.list_futures_contracts(SETTLE)
            for item in exchange_info:
                symbol_tick_size[item.name] = {
                    'tick_size': len(str(float(item.order_price_round)).split('.')[-1].rstrip('0')),
                    'min_qty': len(str(float(item.order_size_min)).split('.')[-1].rstrip('0')),
                    "qty_to_contract": float(item.quanto_multiplier),
                    "order_price_round": float(item.order_price_round)
                }

                # if item.name == "BNB_USDT":
                #     print(item)
                #     print(symbol_tick_size[item.name])
            self.logger.info(f'获取币种精度成功')
        except GateApiException as ex:
            self.logger.error(f'获取币种精度失败，错误: {ex}')

    def amountConvertToContract(self, _symbol, _amount):
        """将数量转换为张数"""
        global symbol_tick_size
        qty_to_contract = symbol_tick_size[_symbol]['qty_to_contract']
        return int(_amount / qty_to_contract)

    def round_to_step(self, price, step, decimal_places):
        """将价格四舍五入到最小步长的倍数"""
        # 将价格除以步长，四舍五入到整数，然后再乘以步长
        rounded = round(price / step) * step
        # 保留指定小数位
        return round(rounded, decimal_places)
    
    def monitor_new_coin(self, symbol):
        """监控新币上线及交易条件"""
        self.logger.info(f"gateio开始监控新币: {symbol}")
        
        # 获取账户余额信息
        try:
            account_info = self.get_account()
            if account_info:
                self.logger.info(f"账户余额信息: {json.dumps(account_info.to_dict(), ensure_ascii=False, indent=2)}")
            else:
                self.logger.error("获取账户余额失败")
        except Exception as e:
            self.logger.error(f"获取账户余额异常: {str(e)}")
                            
        # 检查合约是否存在
        symbol_exists = False
        tick_size = 0
        
        while True:
            try:
                if symbol_exists == False:
                    # 获取所有可交易的合约信息
                    contracts = self.futures_api.list_futures_contracts(SETTLE)

                    for contract in contracts:
                        if contract.name == symbol:
                            symbol_exists = True
                            # 获取合约的精度信息
                            tick_size = len(str(float(contract.order_price_round)).split('.')[-1].rstrip('0'))
                            self.logger.info(f"gateio-{symbol}合约精度信息: tick_size={tick_size}")
                            self.logger.info(f"gateio-{symbol} 合约已上线")
                            break
                
                if symbol_exists:
                    # 获取4小时K线数据
                    klines = self.futures_api.list_futures_candlesticks(
                        SETTLE, 
                        symbol, 
                        interval="4h", 
                        limit=3
                    )
                    
                    if len(klines) >= 3:
                        # 计算前两根K线的跌幅
                        prev_open = float(klines[1].o)    # 倒数第二根K线开盘价
                        prev_close = float(klines[1].c)   # 倒数第二根K线收盘价
                        
                        prev_prev_open = float(klines[0].o)    # 倒数第三根K线开盘价
                        prev_prev_close = float(klines[0].c)   # 倒数第三根K线收盘价
                        
                        # 获取资金费率
                        funding_rate_info = self.futures_api.list_futures_funding_rate_history(
                            SETTLE, 
                            symbol, 
                            limit=1
                        )
                        funding_rate = float(funding_rate_info[0].r) if funding_rate_info else 0
                        
                        # 获取标记价格
                        mark_price = self.get_mark_price(symbol)
                        
                        funding_rate_limit = float(STRATEGY_CONFIG['funding_rate_limit']) / 100
                        # 判断是否满足做空条件
                        is_bearish = (prev_close < prev_open and 
                                    prev_prev_close < prev_prev_open and 
                                    funding_rate > funding_rate_limit)  # 资金费率大于配置的阈值
                        # is_bearish = True
                        if is_bearish:
                            try:
                                self.logger.info(f"{symbol} | 倒数第二根K线开盘价: {prev_open}, 收盘价: {prev_close} | 倒数第三根K线开盘价: {prev_prev_open}, 收盘价: {prev_prev_close} | 当前资金费率: {funding_rate}, 资金费率阈值: {funding_rate_limit}")
                                # 发送满足条件的警报
                                alert_msg = f"gateio-{symbol} 满足做空条件:\n" \
                                          f"倒数第二根K线跌幅: {((prev_close-prev_open)/prev_open*100):.2f}%\n" \
                                          f"倒数第三根K线跌幅: {((prev_prev_close-prev_prev_open)/prev_prev_open*100):.2f}%\n" \
                                          f"当前资金费率: {funding_rate*100:.2f}%\n" \
                                          f"当前标记价格: {mark_price}"
                                self.send_wx_notification(f"gateio-{symbol}空", alert_msg)
                                # 获取账户余额
                                account_info = self.get_account()
                                available_balance = float(account_info.available) if account_info else 0
                                
                                entry_usdt_percent = float(STRATEGY_CONFIG['entry_usdt_percent'])
                                # 计算入场金额（使用账户余额的指定比例）
                                entry_usdt = available_balance * entry_usdt_percent
                                
                                # 计算入场价格（当前标记价格上浮0.1%）
                                entry_price = round(mark_price * 1.001, tick_size)

                                # 计算下单数量
                                quantity = self.amountConvertToContract(symbol, entry_usdt / entry_price)
                                
                                self.logger.info(f"{symbol}做空入场: 账户余额:{available_balance}|"
                                               f"入场金额:{entry_usdt}|入场价格:{entry_price}|"
                                               f"数量:{quantity}")
                                
                                # 开空单
                                order_id = self.place_order(
                                    symbol=symbol,
                                    side="sell",
                                    qty=quantity,
                                    price=entry_price,
                                    order_type="limit"
                                )
                                
                                if order_id:
                                    self.logger.info(f"开空单成功，订单ID: {order_id}")
                                    
                                    # 发送通知
                                    msg = f"gateio-{symbol} 开空成功:\n" \
                                          f"价格: {mark_price}\n" \
                                          f"数量: {quantity}\n" \
                                          f"订单ID: {order_id}"
                                    self.send_wx_notification("新币监控", msg)
                                    
                                    # 开仓成功后退出循环
                                    self.logger.info(f"{symbol} 开仓成功，退出监控循环")
                                    return True
                                    
                                else:
                                    self.logger.error(f"开空单失败")
                                    self.send_wx_notification("新币监控", 
                                                           f"{symbol} 开空单失败")
                                    
                            except GateApiException as e:
                                error_msg = f"开空单异常: {str(e)}"
                                self.logger.error(error_msg)
                                self.send_wx_notification("新币监控", error_msg)
                                return
                
            except Exception as e:
                self.logger.error(f"监控新币异常: {str(e)}")
                return True
            
            time.sleep(60)  # 每分钟检查一次

