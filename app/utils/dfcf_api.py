import hashlib
import json
import os
import random
import string
import time
from datetime import datetime
from urllib.parse import quote  # 添加这行导入
from app.utils.logger import get_logger

import requests
from curl_cffi import requests as c_requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

os.environ['REQUESTS_CA_BUNDLE'] = requests.utils.DEFAULT_CA_BUNDLE_PATH

logger = get_logger(__name__)

config = {
    'http':True,
    'is_proxy':False
}
def get_proxy():
    """获取代理配置"""
    base_username = 'B_58204_hk___90_{random}'
    password = 'ipwebgz'
    host = 'gate3.ipweb.cc'
    port = '7778'

    proxy_config = {}
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
    username = base_username.replace('{random}', random_suffix)

    if config['http']:
        proxy_url = f"http://{username}:{password}@{host}:{port}"
        proxy_config['http'] = proxy_url
        proxy_config['https'] = proxy_url
        config['http'] = False
    else:
        proxy_url = f"stock5://{username}:{password}@{host}:{port}"
        proxy_config['stock5'] = proxy_url
        config['http'] = True
    return proxy_config


class DFCJStockApi:
    """
        东方财富网 数据api
            url：https://so.eastmoney.com
    """

    def __init__(self):

        # 在初始化session时配置
        # self.session = requests.Session()
        # self.session.trust_env = False  # 不读取系统代理设置

        # # 配置适配器
        # adapter = requests.adapters.HTTPAdapter(
        #     pool_connections=10,
        #     pool_maxsize=10,
        #     max_retries=3,
        #     pool_block=False
        # )
        # self.session.mount('http://', adapter)
        # self.session.mount('https://', adapter)
        # self.session.verify = requests.utils.DEFAULT_CA_BUNDLE_PATH


        # 生成随机浏览器指纹
        self.ut_fixed = None
        self.browser_fingerprint = self._get_random_browser_fingerprint()
        # 创建支持指纹伪装的session
        self.session = c_requests.Session(impersonate=self.browser_fingerprint)
        # 使用随机headers初始化session
        self.session.headers.update(self._generate_random_headers())

        self.session.verify = requests.utils.DEFAULT_CA_BUNDLE_PATH

        self.logger = get_logger(self.__class__.__name__)

    def _get_random_browser_fingerprint(self):
        """获取随机Chrome浏览器指纹（用于TLS指纹伪装）"""
        # curl_cffi 官方支持的 Chrome 版本列表（根据官方文档）
        # 支持的版本：chrome99, chrome100, chrome101, chrome104, chrome107, 
        # chrome110, chrome116, chrome119, chrome120, chrome123, chrome124, 
        # chrome131, chrome133a, chrome136
        chrome_versions = [
            'chrome124', 'chrome131', 'chrome133a', 'chrome136',
        ]
        return random.choice(chrome_versions)
    
    def _generate_random_user_agent(self):
        """生成随机Chrome User-Agent"""
        # 根据浏览器指纹生成对应的Chrome User-Agent
        fingerprint = self.browser_fingerprint
        
        # 处理特殊版本号（如 chrome133a）
        if fingerprint == 'chrome133a':
            version = '133'
        else:
            version = fingerprint.replace('chrome', '')
        
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"

    def _generate_random_headers(self, referer=None):
        """生成随机请求头"""
        # 随机Accept-Language
        accept_languages = [
            "zh-CN,zh;q=0.9",
            "zh-CN,zh;q=0.9,en;q=0.8",
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        ]
        accept_language = random.choice(accept_languages)
        
        # 随机Sec-Fetch-Dest值
        sec_fetch_dests = ["script", "empty", "document"]
        sec_fetch_dest = random.choice(sec_fetch_dests)
        
        # 随机Sec-Fetch-Mode值
        sec_fetch_modes = ["no-cors", "cors", "same-origin"]
        sec_fetch_mode = random.choice(sec_fetch_modes)
        
        headers = {
            "Accept": "*/*",
            "Accept-Language": accept_language,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": sec_fetch_dest,
            "Sec-Fetch-Mode": sec_fetch_mode,
            "Sec-Fetch-Site": "same-site",
            # "User-Agent": self._generate_random_user_agent(),
        }
        
        # 如果有Referer，添加它
        if referer:
            headers["Referer"] = referer
        
        return headers


    @retry(
        stop=stop_after_attempt(5),  # 最多尝试5次
        wait=wait_exponential(multiplier=1, min=2, max=30),  # 指数退避：2s, 4s, 8s, 16s, 30s...
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def __get(self,*args, **kwargs):
        # # 每次请求随机更换浏览器指纹（更难以识别）
        # if random.random() < 0.3:  # 30% 概率更换指纹
        #     self.browser_fingerprint = self._get_random_browser_fingerprint()
        #     # 重新创建session以应用新的指纹
        #     old_proxies = getattr(self.session, 'proxies', {})
        #     self.session = requests.Session(impersonate=self.browser_fingerprint)
        #     if old_proxies:
        #         self.session.proxies.update(old_proxies)
        # username = "B_58204_hk___90_{random}".replace("{random}", ''.join(random.choices(string.ascii_lowercase + string.digits, k=11)))
        # # 设置代理
        # proxies = {
        #     "http": f"http://{username}:ipwebgz@gate2.ipweb.cc:7778",
        #     "https": f"http://{username}:ipwebgz@gate2.ipweb.cc:7778"
        # }
        # 如果未传递headers，则使用随机headers
        if 'headers' not in kwargs:
            # 更新session的headers为随机值
            self.session.headers.update(self._generate_random_headers())

        if config['is_proxy']:
            proxy = get_proxy()
            self.logger.info(proxy)
            response = self.session.get(*args, **kwargs,proxies=proxy)
        else:
            response = self.session.get(*args, **kwargs)
        # gate2.ipweb.cc
        # 7778
        # B_58204_hk___90_95f186fa599
        # ipwebgz
        response.raise_for_status()
        return response


    def get_stock_kline_data(self, stock_code, stock_type, limit=100, kline_type='101'):
        """
        获取股票K线数据

        Args:
            stock_code (str): 股票代码
            stock_type (str): 交易所代码
            limit (int): 获取数据条数
            kline_type (str): K线类型 (101=日K, 102=周K, 103=月K, 5=5分钟, 15=15分钟, 30=30分钟, 60=60分钟)
                     *  5(5分钟)，15(15分钟)，30(30分钟)，60(60分钟)，101(日)，102(周)，103(月)，104(季)，105(半年)，106(年)

        Returns:
            list: K线数据列表
        """
        try:
            # 构建东方财富API URL
            url = self._build_eastmoney_url(stock_type, stock_code, limit, kline_type)
            if not url:
                self.logger.error("无法构建东方财富API URL，参数可能不正确")
                return []

            self.logger.debug(f"请求东方财富K线接口: {url}")
            response = self.__get(url, timeout=10)
            if response.status_code != 200:
                self.logger.error(f"请求失败: {response.status_code}")
                return []

            data = response.json()

            if 'data' not in data or 'klines' not in data['data']:
                self.logger.error(f"数据格式错误: {data}")
                return []

            # 解析K线数据
            kline_data = []
            for line in data['data']['klines']:
                kline = self._parse_kline_data(line, data['data']['code'])
                if kline:
                    kline_data.append(kline)

            self.logger.info(f"获取K线数据成功，记录数: {len(kline_data)} code={stock_code}")
            return kline_data

        except Exception as e:
            raise e


    def generate_wbp2u(self):
        """生成 wbp2u 参数"""
        timestamp = int(time.time() * 1000) * 1000 + random.randint(0, 9999)
        return f"{timestamp}|0|1|0|web"

    def get_ut(self, use_random=False):
        """获取 ut 参数"""
        if use_random:
            raw_string = f"{time.time()}{random.random()}"
            return hashlib.md5(raw_string.encode()).hexdigest()
        else:
            return self.ut_fixed

    def _build_eastmoney_url(self, stock_type, stock_code,  limit,kline_type='101'):
        """构建东方财富API URL"""
        """构建东方财富API URL"""
        base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

        ut = self.get_ut(True)
        secid = f"{stock_type}.{stock_code}"
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": ut,
            "secid": secid,
            "dect": "1",
            "klt": kline_type,
            "lmt": str(limit),
            "fqt": "1",
            "forcect": "1",
            "end": "20500000",
            "wbp2u":self.generate_wbp2u(),
            # "cb": "__jp0"
        }

        # 构建查询字符串
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        built = f"{base_url}?{query_string}"
        self.logger.debug(f"构建的URL: {built}")
        return built


    def _parse_kline_data(self, line, stock_code):
        """解析K线数据"""
        try:
            data = line.split(',')
            if len(data) < 10:
                logger.warning(f"K线原始数据字段数量不足: {line}")
                return None
            # return [
            #     data[0],
            #     data[1],
            #     data[2],
            #     data[3],
            #     data[4],
            #     data[5],
            #     data[6],
            #     f"{data[7]}%",
            #     data[10],
            #     data[8],
            #     data[9],
            #     float(data[9]),
            # ]
            return {
                'stock_code': stock_code,
                'stock_date': data[0],
                'stock_kp': float(data[1]),  # 开盘价
                'stock_sp': float(data[2]),  # 收盘价
                # 'stock_zg': float(data[3]),  # 最高价
                # 'stock_zd': float(data[4]),  # 最低价
                # 'stock_cjl': int(data[5]),  # 成交量
                # 'stock_cje': float(data[6]) if len(data) > 6 else 0,  # 成交额
                # 'stock_zf': float(data[7]) if len(data) > 7 else 0,  # 振幅%
                # 'stock_zdf': float(data[8]) if len(data) > 8 else 0,  # 涨跌幅%
                # 'stock_zde': float(data[9]) if len(data) > 9 else 0,  # 涨跌额
                # 'stock_hsl': float(data[10]) if len(data) > 10 else 0,  # 换手率%
                # 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            logger.exception("解析K线数据失败")
            return None

    def get_search_list_by_stock_code(self, stock, page_size=20):
        """
        通过股票代码或名称搜索股票信息，返回所有搜索结果

        Args:
            stock (str): 股票代码或名称，如 "TSM" 或 "台积电"
            page_size (int): 返回结果数量，默认20条

        Returns:
            list: 搜索结果列表，如果出错则返回包含error的字典
        """
        # 生成随机headers，包含动态Referer
        referer = f"https://so.eastmoney.com/web/s?keyword={quote(stock)}"
        headers = self._generate_random_headers(referer=referer)
        param = json.dumps({
            "uid": "",
            "keyword": stock,
            "type": [
                "codetable"
            ],
            "client": "web",
            "clientVersion": "curr",
            "clientType": "web",
            "param": {
                "codetable": {
                    "pageSize": page_size,
                    "pageIndex": 1,
                    "postTag": "",
                    "preTag": "",
                }
            }
        }, ensure_ascii=False)

        def generate_jquery_callback():
            random_digits = ''.join([str(random.randint(0, 9)) for _ in range(16)])
            timestamp = str(int(time.time() * 1000))
            callback_name = f"jQuery{random_digits}_{timestamp}"
            return callback_name

        try:
            url = "https://search-api-web.eastmoney.com/search/jsonp"
            params = {
                'cb': generate_jquery_callback(),
                "param": param,
                "_": str(int(time.time() * 1000))
            }
            self.logger.debug(f"请求东方财富搜索接口（列表）: {url} params={params}")
            response = self.__get(url, headers=headers, params=params)
            json_str = response.text
            self.logger.debug(f"接口url:{response.url}\n 搜索接口返回数据: {json_str}")
            # 检查响应是否包含有效的JSONP格式
            if '(' in json_str and ')' in json_str:
                json_str = json_str[json_str.find('(') + 1:json_str.rfind(')')]
                json_data = json.loads(json_str)

                # 检查返回的数据结构是否符合预期
                if "result" in json_data and "codetable" in json_data["result"]:
                    codetable = json_data["result"]["codetable"]
                    if codetable and len(codetable) > 0:
                        return codetable  # 返回所有结果
                    else:
                        self.logger.warning("搜索接口返回空结果")
                        return []
                else:
                    self.logger.error("搜索接口返回数据格式不正确")
                    return {"error": "数据格式错误"}
            else:
                self.logger.error("搜索接口返回非JSONP格式数据")
                return {"error": "响应格式错误"}

        except json.JSONDecodeError as je:
            self.logger.exception("搜索接口返回数据无法解析为JSON")
            return {"error": f"JSON解析失败: {str(je)}"}
        except Exception as e:
            self.logger.exception("搜索接口调用失败")
            return {"error": f"未知错误: {str(e)}"}


if __name__ == '__main__':
    api = DFCJStockApi()
    # print(api.get_search_list_by_stock_code('LMT', 10))
    print(api.get_search_list_by_stock_code('000001', 10))
    # print(api.get_stock_kline_data("600519",'1',400,'1'))
    # print(requests.get('http://cip.cc', proxies=proxies).text)