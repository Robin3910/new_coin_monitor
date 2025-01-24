from flask import Flask, request
import json
import requests

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def receive_message():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # 提取消息内容
            msg_type = data.get('type')
            message = data.get('message')
            currency = data.get('currency')
            exchange = data.get('exchange')
            
            # 组装要发送的消息
            content = f"新币：{currency} 已在 {exchange} 上线"
            
            # 发送到虾推啥（替换成你的KEY）
            xts_key = ""
            xts_url = f"https://wx.xtuis.cn/{xts_key}.send?text={content}"
            requests.get(xts_url)
            
            # 发送到方糖Server酱（替换成你的KEY）
            ftqq_key = ""
            ftqq_url = f"https://sctapi.ftqq.com/{ftqq_key}.send?title={content}"
            # params = {
            #     "title": f"新币上线：{currency}",
            #     "desp": content
            # }
            requests.get(ftqq_url)
            
            return '', 200
        except Exception as e:
            return str(e), 500
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8088) 