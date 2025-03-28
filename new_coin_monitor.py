# 对接cryptocurrency alerting的通知
# 转发到微信上

from flask import Flask, request
import json
import requests
import threading
import time
from binance.um_futures import UMFutures
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
from enum import Enum
from binance.um_futures import UMFutures as Client
from binance.error import ClientError

from config import BINANCE_CONFIG, WX_CONFIG, STRATEGY_CONFIG

app = Flask(__name__)

# 配置日志
def setup_logger():
    logger = logging.getLogger('new_coin_monitor')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler('new_coin_monitor.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

logger = setup_logger()

api_key = BINANCE_CONFIG['key']
api_secret = BINANCE_CONFIG['secret']
base_url = BINANCE_CONFIG['base_url']

# 初始化币安客户端
client = Client(
    BINANCE_CONFIG['key'], 
    BINANCE_CONFIG['secret'], 
    base_url=BINANCE_CONFIG['base_url']
)

logger.info(client.account())

symbol_tick_size = {}

# 定义交易状态枚举
class TradingStatus(Enum):
    NOT_LISTED = "未上线"
    NOT_QUALIFIED = "未达标"
    ORDER_PLACED = "已挂入场单"
    POSITION_OPENED = "已持仓"
    POSITION_CLOSED = "已出场"

def get_decimal_places(tick_size):
    """
    计算价格精度，只取到第一个非零数字的位置
    例如：
    0.0001000 -> 4
    0.001 -> 3
    1.0 -> 0
    """
    if '.' not in tick_size:
        return 0
    
    decimal_part = tick_size.split('.')[1]
    for i, digit in enumerate(decimal_part):
        if digit != '0':
            return i + 1
    return 0

def update_trading_status(symbol, status, order_id=None, tp_order_id=None, sl_order_id=None):
    """更新交易对状态"""
    try:
        # 读取现有数据
        try:
            with open('trading_pair.json', 'r', encoding='utf-8') as f:
                trading_pairs = json.load(f)
        except FileNotFoundError:
            trading_pairs = {}

        if trading_pairs.get(symbol) is None:
            trading_pairs[symbol] = {
                'status': TradingStatus.NOT_LISTED.value,
                'order_id': None,
                'tp_order_id': None,
                'sl_order_id': None
            }
        trading_pairs[symbol]['status'] = status.value
        trading_pairs[symbol]['order_id'] = order_id
        trading_pairs[symbol]['tp_order_id'] = tp_order_id
        trading_pairs[symbol]['sl_order_id'] = sl_order_id
        
        # 保存更新后的数据
        with open('trading_pair.json', 'w', encoding='utf-8') as f:
            json.dump(trading_pairs, f, ensure_ascii=False, indent=4)
        
        logger.info(f"更新{symbol}状态为: {status.value}, order_id: {order_id}, tp_order_id: {tp_order_id}, sl_order_id: {sl_order_id}")
    except Exception as e:
        logger.error(f"更新交易状态失败: {str(e)}")

def get_trading_info(symbol):
    with open('trading_pair.json', 'r', encoding='utf-8') as f:
        trading_pairs = json.load(f)
    return trading_pairs.get(symbol, {})

def get_account_balance():
    """获取账户USDT余额"""
    try:
        account_info = client.account()
        for asset in account_info['assets']:
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
        return 0
    except Exception as e:
        logger.error(f"获取账户余额失败: {str(e)}")
        return 0

def monitor_new_coin(symbol):
    """监控新币上线及交易条件"""
    logger.info(f"开始监控新币: {symbol}")
    
    # 初始状态设置为未上线
    update_trading_status(symbol, TradingStatus.NOT_LISTED)
    
    # 等待合约上线
    while True:
        try:
            # 检查合约是否存在
            exchange_info = client.exchange_info()
            symbols = [info['symbol'] for info in exchange_info['symbols']]
            if symbol in symbols:
                logger.info(f"{symbol} 合约已上线")
                logger.info(f"精度|tick_size: {exchange_info['symbols'][symbols.index(symbol)]['filters'][0]['tickSize']}|min_qty: {exchange_info['symbols'][symbols.index(symbol)]['filters'][1]['minQty']}")
                symbol_tick_size[symbol] = {
                    'tick_size': get_decimal_places(exchange_info['symbols'][symbols.index(symbol)]['filters'][0]['tickSize']),
                    'min_qty': get_decimal_places(exchange_info['symbols'][symbols.index(symbol)]['filters'][1]['minQty']),
                }
                update_trading_status(symbol, TradingStatus.NOT_QUALIFIED)
                break
            time.sleep(60)  # 每分钟检查一次
        except Exception as e:
            logger.error(f"检查合约状态出错: {str(e)}")
            time.sleep(60)
            continue
    
    # 监控交易条件
    while True:
        try:
            # 获取4小时K线数据
            klines = client.klines(symbol, '4h', limit=3)
            
            if len(klines) >= 3:
                # 计算前两根K线的跌幅
                prev_open = float(klines[-2][1])    # 倒数第二根K线开盘价
                prev_close = float(klines[-2][4])   # 倒数第二根K线收盘价

                prev_prev_open = float(klines[-3][1])    # 倒数第三根K线开盘价
                prev_prev_close = float(klines[-3][4])   # 倒数第三根K线收盘价
                mark_price_info = client.mark_price(symbol)
                funding_rate = float(mark_price_info['lastFundingRate'])
                mark_price = float(mark_price_info['markPrice'])

                trading_info = get_trading_info(symbol)
                # 当前K线跌幅超过配置的百分比才算下跌
                is_bearish = prev_close < prev_open and prev_prev_close < prev_prev_open and funding_rate > STRATEGY_CONFIG['funding_rate_limit']/100 and trading_info.get('status') == TradingStatus.NOT_QUALIFIED.value
                
                if is_bearish:
                    try:
                        # 获取账户余额并计算入场金额
                        account_balance = get_account_balance()
                        entry_usdt = account_balance * 0.5  # 使用账户余额的一半
                        
                        entry_price = round(mark_price * (1 + STRATEGY_CONFIG['entry_price_add_percent'] / 100), 
                                         symbol_tick_size[symbol]['tick_size'])
                        
                        # 计算下单数量
                        quantity = round(entry_usdt/entry_price, symbol_tick_size[symbol]['min_qty'])
                        
                        logger.info(f"{symbol}做空入场: 账户余额:{account_balance}|入场金额:{entry_usdt}|"
                                  f"入场价格:{entry_price}|quantity:{quantity}")

                        # 开空单
                        order = client.new_order(
                            symbol=symbol,
                            side="SELL",
                            type="LIMIT",
                            quantity=quantity,
                            price=entry_price,
                            timeInForce="GTC"
                        )
                        
                        if order['orderId']:
                            update_trading_status(symbol, TradingStatus.ORDER_PLACED, order['orderId'])
                            
                            msg = f"{symbol} 开空成功:\n" \
                                    f"价格: {mark_price}\n" \
                                    f"数量: {quantity}\n" \
                                    f"订单ID: {order['orderId']}"
                            send_notification(msg)
                            logger.info(msg)
                            break
                        else:
                            logger.error(f"开空单失败: {order}")
                            send_notification(f"{symbol} 开空单失败: {order}")
                            
                    except Exception as e:
                        error_msg = f"开空单异常: {str(e)}"
                        logger.error(error_msg)
                        send_notification(error_msg)
            
            time.sleep(10)  # 每5分钟检查一次
            
        except Exception as e:
            logger.error(f"监控交易条件出错: {str(e)}")
            time.sleep(10)
            continue

    # 监控持仓
    while True:
        try:
            # 读取交易状态
            pair_info = get_trading_info(symbol)
            current_status = pair_info.get('status')
            order_id = pair_info.get('order_id')
            
            if current_status == TradingStatus.ORDER_PLACED.value and order_id:
                # 检查订单是否成交
                order = client.query_order(symbol=symbol, orderId=order_id)
                if order['status'] == 'FILLED':
                    entry_price = float(order['avgPrice'])
                    quantity = float(order['executedQty'])
                    
                    # 计算止盈止损价格
                    tp_price = round(entry_price * (1 - STRATEGY_CONFIG['tp_percent'] / 100), 
                                   symbol_tick_size[symbol]['tick_size'])
                    sl_price = round(entry_price * (1 + STRATEGY_CONFIG['sl_percent'] / 100), 
                                   symbol_tick_size[symbol]['tick_size'])
                    
                    logger.info(f"设置止盈: {tp_price}|止损： {sl_price}|入场价格：{entry_price}|数量：{quantity}")
                    
                    # 设置止盈单
                    tp_order = client.new_order(
                        symbol=symbol,
                        side="BUY",
                        type="LIMIT",
                        quantity=quantity,
                        price=tp_price,
                        reduceOnly=True,
                        timeInForce="GTC"
                    )
                    
                    # 设置止损单
                    sl_order = client.new_order(
                        symbol=symbol,
                        side="BUY",
                        type="STOP_MARKET",
                        stopPrice=sl_price,
                        quantity=quantity,
                        reduceOnly=True,
                        timeInForce="GTC"
                    )

                    if tp_order['orderId'] and sl_order['orderId']:
                        # 更新状态为已持仓
                        update_trading_status(
                            symbol, 
                            TradingStatus.POSITION_OPENED,
                            order_id,
                            tp_order['orderId'],
                            sl_order['orderId']
                        )
                        
                        msg = f"{symbol} 入场成功并设置止盈止损:\n" \
                            f"入场价格: {entry_price}\n" \
                            f"止盈价格: {tp_price}\n" \
                            f"止损价格: {sl_price}\n" \
                            f"数量: {quantity}"
                        send_notification(msg)
                        logger.info(msg)
                
            elif current_status == TradingStatus.POSITION_OPENED.value:
                # 检查止盈止损单是否成交
                tp_order_id = pair_info.get('tp_order_id')
                sl_order_id = pair_info.get('sl_order_id')
                
                if tp_order_id:
                    tp_order = client.query_order(symbol=symbol, orderId=tp_order_id)
                    if tp_order['status'] == 'FILLED':
                        del trading_info[symbol]
                        # update_trading_status(symbol, TradingStatus.POSITION_CLOSED)
                        msg = f"{symbol} 止盈成交，交易结束"
                        send_notification(msg)
                        logger.info(msg)
                        break
                
                if sl_order_id:
                    sl_order = client.query_order(symbol=symbol, orderId=sl_order_id)
                    if sl_order['status'] == 'FILLED':
                        del trading_info[symbol]
                        # update_trading_status(symbol, TradingStatus.POSITION_CLOSED)
                        msg = f"{symbol} 止损成交，交易结束"
                        send_notification(msg)
                        logger.info(msg)
                        break
            
            time.sleep(10)  # 每10秒检查一次
        
        except Exception as e:
            logger.error(f"监控持仓出错: {str(e)}")
            time.sleep(10)
            continue

def send_notification(content):
    """发送通知到微信"""
    try:
        # 发送到方糖
        ftqq_url = f"https://sctapi.ftqq.com/{WX_CONFIG['token']}.send?title={content}&desp={content}"
        requests.get(ftqq_url)
        
    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def receive_message():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # 提取消息内容
            currency = data.get('currency')
            exchange = data.get('exchange')
            
            if exchange.upper() == 'BINANCE':
                # 格式化币对名称（添加USDT后缀）
                symbol = f"{currency}USDT"
                
                # 发送新币上线通知
                # content = f"新币：{currency} 已在 {exchange} 上线"
                # send_notification(content)
                
                # 启动监控线程
                monitor_thread = threading.Thread(
                    target=monitor_new_coin,
                    args=(symbol,),
                    daemon=True
                )
                monitor_thread.start()
                
            return '', 200
            
        except Exception as e:
            logger.error(f"处理请求失败: {str(e)}")
            return str(e), 500
            
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088) 