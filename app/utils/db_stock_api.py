#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP请求工具类
用于与股票API进行通信
"""

import requests
import json
import time
from typing import Dict, Optional, Any
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StockAPIClient:
    """股票API客户端"""

    def __init__(self, base_url: str = "http://stockapi.stplan.cn", timeout: int = 30):
        """
        初始化API客户端

        Args:
            base_url: API基础URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

        # 设置默认请求头
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Python Stock Parameter Validator/1.0'
        })

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                      params: Optional[Dict] = None) -> Optional[Dict]:
        """
        发送HTTP请求

        Args:
            method: HTTP方法
            endpoint: API端点
            data: 请求数据
            params: URL参数

        Returns:
            响应数据字典或None
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        logger.debug(f"发送 {method} 请求到 {url}")

        if method.upper() == 'GET':
            response = self.session.get(url, params=params, timeout=self.timeout)
        elif method.upper() == 'POST':
            response = self.session.post(url, json=data, params=params, timeout=self.timeout)
        else:
            raise ValueError(f"不支持的HTTP方法: {method}")

        response.raise_for_status()

        # 检查响应状态
        if response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                logger.warning(f"响应不是有效的JSON格式: {response.text}")
                return {"raw_response": response.text}
        raise requests.HTTPError(f"请求失败，状态码: {response.status_code}, 响应: {response.text}")

    def add_or_modify_stock_param_result(self, result_data: Dict) -> Optional[Dict]:
        """
        调用 StockParamResult/AddOrModify 接口。

        Args:
            result_data: 请求体数据

        Returns:
            接口返回结果字典或带 raw_response 的字典
        """
        url = f"{self.base_url}/api/StockParamResult/AddOrModify"
        headers = {
            "accept": "text/plain",
            "Content-Type": "application/json-patch+json",
            "User-Agent": "Python Stock Parameter Validator/1.0",
        }

        response = self.session.post(
            url,
            headers=headers,
            json=result_data,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if response.status_code == 200:
            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {"raw_response": response.text}
            return result

        raise requests.HTTPError(f"请求失败，状态码: {response.status_code}, 响应: {response.text}")

