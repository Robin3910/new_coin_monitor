import time

from bitmart.api_contract import APIContract
from bitmart.lib.cloud_exceptions import APIException

BM_SUCCESS = 1000

class BitMartAccount:
    def __init__(self, api_key, api_secret, memo, logger):
        self.api_key = api_key
        self.api_secret = api_secret
        self.memo = memo
        self.logger = logger

        self.init_instruments()

    # 账户
    # def get_account_api(self):
    #     return Account(api_key = self.api_key, secret_key = self.api_secret, memo = self.memo)

    # 交易
    def get_trade_api(self):
        return APIContract(api_key = self.api_key, secret_key = self.api_secret, memo = self.memo)

    def get_account_info(self):
        account_info = self.get_trade_api().get_assets_detail()[0]
        if account_info['code'] == BM_SUCCESS:
            return account_info['data']
        return None
    
    # 查看账户余额
    def get_balance(self):
        account_info = self.get_trade_api().get_assets_detail()[0]
        if account_info['code'] == BM_SUCCESS:
            return float(account_info['data'][0]['available_balance'])
        return 0

    def get_decimal_places(self,tick_size):
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
    # 获取公共数据，包含合约面值等信息
    def init_instruments(self):
        c = 0
        try:
            # contractAPI = APIContract(self.api_key, self.api_secret, self.memo)
            
            swapInstrumentsRes = self.get_trade_api().get_details()[0]
            
            # 获取永续合约基础信息
            # swapInstrumentsRes = exchange.publicGetPublicInstruments(params={"instType": "SWAP"})
            if swapInstrumentsRes['code'] == 1000:
                self.swapInstruments = swapInstrumentsRes['data']['symbols']
                self.tickSizeMap = {}
                for i in self.swapInstruments:
                    self.tickSizeMap[i['symbol']] = self.get_decimal_places(i['price_precision'])
                self.logger.info(f"{self.api_key}永续合约基础信息: {self.swapInstruments}")
                self.logger.info(f"{self.api_key}永续合约tickSizeMap: {self.tickSizeMap}")
                c = c + 1
        except Exception as e:
            self.logger.info(f"{self.api_key}-publicGetPublicInstruments 失败" + str(e))
            # self.okx_helper.send_wx_notification(f"{self.api_key}获取合约信息失败", f"获取合约信息失败: {str(e)}")
        
        return c >= 2
    
            # 获取合约面值
    def getFaceValue(self, _symbol):
        swapInstrumentsRes = self.get_trade_api().get_details(contract_symbol=_symbol)[0]

        if swapInstrumentsRes['code'] == BM_SUCCESS:
            return float(swapInstrumentsRes['data']['symbols'][0]['contract_size'])
        return False


    # 将 amount 币数转换为合约张数
    # 币的数量与张数之间的转换公式
    # 单位是保证金币种（币本位的币数单位为币，U本位的币数单位为U）
    # 1、币本位合约：币数=张数*面值*合约乘数/标记价格
    # 2、U本位合约：币数=张数*面值*合约乘数*标记价格
    # 交割合约和永续合约合约乘数都是1
    def amountConvertToSZ(self,_symbol, _amount):
        faceValue = self.getFaceValue(_symbol)
        if faceValue is False:
            raise Exception("bitmart getFaceValue error.")
        # U本位合约：张数 = 币数 / 面值 / 合约乘数
        sz = float(_amount) / faceValue / 1
        return int(sz)
