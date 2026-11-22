# -*- coding: utf-8 -*-
"""
day10 / utils / AI_HttpClient.py

基于 requests 二次封装的 HTTP 客户端，核心能力：
    1. 自定义 HttpError 异常，携带原始 response 对象，失败时仍能读取响应体；
    2. 内置 requests.Session 复用 TCP 连接，避免每次请求重建连接池；
    3. 挂载 urllib3 Retry，对 500/502/503/504 自动重试并按 backoff_factor 退避；
    4. 统一超时与异常处理，requests 的原始异常全部转换为 HttpError，并用 from e 保留异常链；
    5. 核心 request 支持 params / json_body / data / files / headers / timeout / expect_status；
    6. 提供 get/post/put/delete/patch 与 get_json/post_json 便捷方法；
    7. 内置令牌管理：login() 登录后自动保存令牌，后续请求自动携带 Authorization 头；
    8. 支持 close() 与 with 语法，自动释放连接；
    9. 全程使用 logging 输出请求与响应日志，不使用 print。

本文件不依赖任何项目内其他模块，可独立运行：
    python AI_HttpClient.py
"""

# 标准库：类型注解
from typing import Any, Dict, List, Optional, Tuple, Union

# 第三方库：requests 及适配器
import requests
from requests.adapters import HTTPAdapter

# 第三方库：urllib3 的重试策略
from urllib3.util.retry import Retry

# 标准库：日志
import logging

# ============================================================================
# 1. 配置日志
#    日志格式固定为 "%(asctime)s [%(levelname)s] %(message)s"，
#    便于在测试报告中直接粘贴使用
# ============================================================================

# 创建模块级 logger，名称与本模块一致，便于按名字单独调整级别
logger = logging.getLogger("AI_HttpClient")

# 配置根日志处理器与格式。level=INFO 保证请求与响应日志都能输出，
# 又不会打印 urllib3 的底层调试噪音
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# 响应体在日志中的最大截取长度，避免大响应把日志刷爆
LOG_BODY_MAX_LENGTH = 500


# ============================================================================
# 2. 自定义异常
# ============================================================================

class HttpError(Exception):
    """HTTP 调用过程中抛出的统一异常。

    相比直接抛 requests 的原生异常，本异常额外携带 response 对象：
    上层捕获后仍能读取状态码、响应头与响应体，
    这在断言失败、错误信息提取、AI 排错时非常关键。

    构造方法刻意把 response 设为仅关键字参数（*），
    强制调用方显式写出 response=resp，避免位置传参造成语义混淆。
    """

    def __init__(self, message: str, *, response: Optional[requests.Response] = None) -> None:
        """初始化异常并保存原始响应对象。

        :param message: 异常描述信息
        :param response: 触发该异常的原始响应对象，可为 None。
                         网络层异常（超时、连接失败）时没有响应，此处为 None；
                         状态码断言失败时传入真实响应，上层可读取其响应体。
        """
        # 调用父类初始化，把 message 作为异常的字符串表示
        super().__init__(message)
        # 保存异常描述，便于上层单独取用而不必解析 str(e)
        self.message = message
        # 保存原始响应对象，这是本异常相对 requests 原生异常的核心增量
        self.response = response
        # 记录状态码，网络异常场景为 None
        self.status_code = response.status_code if response is not None else None
        # 记录响应体文本，网络异常场景为 None
        self.response_text = response.text if response is not None else None

    def __str__(self) -> str:
        """返回带状态码的可读描述，便于日志输出。

        :return: 异常描述字符串
        """
        # 有响应时附带状态码与截断后的响应体，无响应时只返回原始描述
        if self.response is not None:
            body = (self.response_text or "")[:LOG_BODY_MAX_LENGTH]
            return "{} (status={}, body={})".format(self.message, self.status_code, body)
        # 网络层异常：没有响应可读，仅返回描述
        return self.message


# ============================================================================
# 3. 核心客户端
# ============================================================================

class HttpClient:
    """封装 requests.Session 的 HTTP 客户端。

    典型用法：

        with HttpClient(base_url="http://localhost:8000") as client:
            resp = client.get("/api/v1/health", expect_status=200)
            data = client.get_json("/api/v1/health")

    相比直接调用 requests.get()，本类提供：
        - 连接复用（Session + 连接池）
        - 失败自动重试（仅对 500/502/503/504 等服务端错误）
        - 统一异常类型（HttpError）
        - 状态码断言（expect_status）
        - 令牌自动管理（login 一次，后续请求自动带 Authorization）
        - 请求响应日志
    """

    def __init__(
        self,
        base_url: str = "",
        headers: Optional[Dict[str, str]] = None,
        timeout: Union[float, Tuple[float, float]] = 10,
        retries: int = 2,
        backoff: float = 0.3,
        verify: bool = True,
    ) -> None:
        """创建并配置客户端。

        :param base_url: 服务基础地址。为空时调用方需在每个路径里带全地址
        :param headers: 会话级默认请求头
        :param timeout: 超时时间。标量表示连接与读取共用；
                        元组 (连接, 读取) 可分别指定
        :param retries: 最大重试次数
        :param backoff: 重试退避基数，单位秒
        :param verify: 是否校验 HTTPS 证书
        """
        # 保存基础地址。去掉末尾斜杠，避免拼接时出现双斜杠
        self.base_url = (base_url or "").rstrip("/")
        # 保存超时配置
        self.timeout = timeout
        # 保存重试与退避配置，便于日志与调试时查看
        self.retries = retries
        self.backoff = backoff
        # 保存证书校验开关
        self.verify = verify

        # 保存访问令牌，初始为空表示尚未登录。
        # 令牌由 set_access_token() 写入，request() 会自动附加到每次请求，
        # 调用方无需在每一处重复书写 Authorization 头
        self.access_token: str = ""

        # 创建 Session 对象。Session 自带连接池，能复用 TCP 连接与 TLS 握手，
        # 这是多次请求场景下相比 requests.get() 最直接的收益
        self.session = requests.Session()

        # 若调用方传入了默认请求头，写入会话，后续请求自动继承
        if headers:
            self.session.headers.update(headers)

        # 配置重试策略并挂载到 Session
        self._mount_adapters()

    def _mount_adapters(self) -> None:
        """构造 urllib3 Retry 策略并挂载到 http:// 与 https://。

        raise_on_status=False 是关键：重试耗尽后不抛 RetryError，
        而是把最后一个响应正常返回给上层。
        这样上层能拿到真实的 Response 对象，据此做状态码断言并读取响应体，
        不会出现「异常直接抛出，响应内容全部丢失」的情况。
        """
        # 构造 urllib3 重试策略
        retry = Retry(
            # 总重试次数
            total=self.retries,
            # 退避系数，等待时间按 backoff * 2^(重试序号-1) 递增
            backoff_factor=self.backoff,
            # 仅对以下服务端错误状态码重试。
            # 4xx 属于客户端错误，重试没有意义，故不在列表中
            status_forcelist=[500, 502, 503, 504],
            # 允许重试的 HTTP 方法。读取类方法可安全重试，
            # 但这里包含 POST，是因为很多后端接口是幂等写入，重试能提升成功率
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
            # 重试耗尽后不自动抛错，交由上层通过 expect_status 校验
            raise_on_status=False,
        )
        # 创建适配器，并把连接池上限设为重试次数 + 1，
        # 保证并发时每个重试线程都有独立可用连接
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=self.retries + 1)
        # 分别挂载到 http 与 https，两种协议都能享受重试能力
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------
    # 3.1 内部工具方法
    # ------------------------------------------------------------------

    def _build_url(self, path: str) -> str:
        """拼接最终请求地址。

        :param path: 接口路径。传绝对 URL 时直接返回，
                     传普通路径且配置了 base_url 时进行拼接。
        :return: 最终请求地址
        """
        # 判断是否为绝对 URL（以 http:// 或 https:// 开头）
        if path.startswith("http://") or path.startswith("https://"):
            # 绝对地址已包含完整信息，直接返回，不做拼接
            return path
        # 未配置 base_url 时无法拼接，原样返回由上层决定如何处理
        if not self.base_url:
            return path
        # 拼接基础地址与路径，避免出现双斜杠
        return "{}/{}".format(self.base_url, path.lstrip("/"))

    def _merge_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """合并请求头：默认头与调用方传入的头叠加。

        传入的同名头会覆盖默认头。返回新字典，不修改全局或 Session 上的头。

        :param headers: 调用方本次请求附加的请求头，可为 None
        :return: 合并后的请求头字典
        """
        # 以默认头为基底，Content-Type 声明请求体为 JSON
        merged = {"Content-Type": "application/json"}
        # 若调用方传入了头，则逐项覆盖默认值
        if headers:
            merged.update(headers)
        # 返回合并结果
        return merged

    def _truncate(self, text: str) -> str:
        """截断文本用于日志输出。

        :param text: 原始文本
        :return: 截断后的文本
        """
        # 文本为空时直接返回空串
        if not text:
            return ""
        # 超出最大长度时截断并追加省略标记，标明内容被截短
        if len(text) > LOG_BODY_MAX_LENGTH:
            return text[:LOG_BODY_MAX_LENGTH] + "...(truncated)"
        # 未超长时原样返回
        return text

    # ------------------------------------------------------------------
    # 3.2 核心请求方法
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        data: Optional[Union[Dict[str, Any], List[Tuple[str, Any]]]] = None,
        files: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Union[float, Tuple[float, float], None] = None,
        expect_status: Optional[Union[int, List[int]]] = 200,
        allow_redirects: bool = True,
    ) -> requests.Response:
        """所有请求的统一出口。

        :param method: HTTP 方法，如 GET、POST、PUT、DELETE
        :param path: 接口路径或绝对 URL
        :param params: 查询字符串参数
        :param json_body: 以 JSON 序列化的请求体
        :param data: 表单或原始请求体
        :param files: 文件上传参数，值可为文件对象、字节或 (文件名, 内容, MIME) 元组
        :param headers: 本次请求附加的请求头
        :param timeout: 本次请求的超时时间，None 表示用实例配置
        :param expect_status: 期望的状态码。int 表示单值，list 表示多个都算通过。
                              None 表示不校验状态码
        :param allow_redirects: 是否允许跟随重定向
        :return: requests.Response 对象
        :raises HttpError: 网络层异常，或状态码与 expect_status 不符
        """
        # 第 1 步：拼接最终请求地址
        url = self._build_url(path)

        # 第 2 步：合并请求头。
        # 已登录时自动附加 Authorization，调用方无需手工传递
        request_headers = self._merge_headers(headers)
        if self.access_token:
            request_headers["Authorization"] = "Bearer " + self.access_token

        # 第 3 步：组装请求参数
        kwargs: Dict[str, Any] = {
            "timeout": timeout if timeout is not None else self.timeout,
            "allow_redirects": allow_redirects,
        }
        if params is not None:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body
        if data is not None:
            kwargs["data"] = data
        if files is not None:
            kwargs["files"] = files
        kwargs["headers"] = request_headers

        # 第 4 步：打印请求日志，方便在报告中核对发了什么
        logger.info(">>> %s %s params=%s", method.upper(), url, params)
        if json_body is not None:
            logger.info(">>> body(json)=%s", json_body)

        # 第 5 步：发起请求。
        # 网络层异常统一转换为 HttpError，让上层不必了解 requests 的异常细节
        try:
            response = self.session.request(method=method.upper(), url=url, **kwargs)
        except requests.RequestException as error:
            logger.error("<<< 请求失败 %s %s: %s", method.upper(), url, error)
            raise HttpError("请求 {} {} 失败: {}".format(method.upper(), url, error)) from error

        # 第 6 步：打印响应日志
        logger.info("<<< %s %s", response.status_code, url)
        logger.info("<<< body=%s", self._truncate(response.text))

        # 第 7 步：状态码校验。
        # 不符合期望时抛 HttpError，并把真实响应带上，
        # 上层能拿到响应体做 AI 排错
        if expect_status is not None:
            allowed = expect_status if isinstance(expect_status, (list, tuple)) else [expect_status]
            if response.status_code not in allowed:
                message = "期望状态码 {}, 实际 {}".format(
                    list(allowed) if len(allowed) > 1 else allowed[0],
                    response.status_code,
                )
                logger.error("<<< 状态码不符: %s", message)
                raise HttpError(message, response=response)

        # 第 8 步：返回响应对象
        return response

    # ------------------------------------------------------------------
    # 3.3 快捷方法
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs) -> requests.Response:
        """发送 GET 请求。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: requests.Response 对象
        """
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        """发送 POST 请求。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: requests.Response 对象
        """
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        """发送 PUT 请求。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: requests.Response 对象
        """
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        """发送 DELETE 请求。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: requests.Response 对象
        """
        return self.request("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs) -> requests.Response:
        """发送 PATCH 请求。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: requests.Response 对象
        """
        return self.request("PATCH", path, **kwargs)

    # ------------------------------------------------------------------
    # 3.4 JSON 便捷方法
    # ------------------------------------------------------------------

    def get_json(self, path: str, **kwargs) -> Any:
        """发送 GET 请求并直接返回解析后的 JSON。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: 解析后的响应体
        """
        response = self.get(path, **kwargs)
        return self.parse_json(response)

    def post_json(self, path: str, **kwargs) -> Any:
        """发送 POST 请求并直接返回解析后的 JSON。

        :param path: 接口路径
        :param kwargs: 透传给 request() 的参数
        :return: 解析后的响应体
        """
        response = self.post(path, **kwargs)
        return self.parse_json(response)

    @staticmethod
    def parse_json(response: requests.Response) -> Any:
        """把响应体解析为 JSON，解析失败时抛出可读异常。

        :param response: requests.Response 对象
        :return: 解析后的数据
        :raises HttpError: 响应体不是合法 JSON
        """
        try:
            return response.json()
        except ValueError as error:
            body = (response.text or "")[:LOG_BODY_MAX_LENGTH]
            raise HttpError(
                "响应不是合法 JSON，原始内容: {}".format(body),
                response=response,
            ) from error

    # ------------------------------------------------------------------
    # 3.5 令牌管理
    # ------------------------------------------------------------------

    def set_access_token(self, token: str) -> None:
        """设置访问令牌，后续请求自动携带。

        :param token: 登录接口返回的 access_token
        """
        self.access_token = token or ""

    def clear_access_token(self) -> None:
        """清除访问令牌，恢复为未登录状态。"""
        self.access_token = ""

    @property
    def is_authenticated(self) -> bool:
        """是否已持有有效令牌。

        :return: True 表示已登录
        """
        return bool(self.access_token)

    def login(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        expect_status: int = 200,
        token_field: str = "access_token",
    ) -> requests.Response:
        """执行登录并自动保存令牌。

        登录成功后从响应中取出令牌字段，调用 set_access_token() 保存，
        之后所有请求自动携带 Authorization 头。

        :param path: 登录接口路径
        :param payload: 登录请求体，通常是 {"username": ..., "password": ...}
        :param expect_status: 期望的状态码
        :param token_field: 令牌在响应体中的字段名
        :return: requests.Response 对象
        :raises HttpError: 登录失败或响应里没有令牌字段
        """
        # 发送登录请求。状态码不符时 request() 内部抛 HttpError
        response = self.request(
            "POST", path, json_body=payload, expect_status=expect_status
        )

        # 解析响应体并取令牌
        try:
            data = response.json()
        except ValueError as error:
            raise HttpError(
                "登录响应不是合法 JSON", response=response
            ) from error

        # 取令牌字段。取不到说明接口契约变了，要明确报错
        token = data.get(token_field) if isinstance(data, dict) else None
        if not token:
            raise HttpError(
                "登录响应中未找到令牌字段 {}".format(token_field),
                response=response,
            )

        # 保存令牌，后续请求自动携带
        self.set_access_token(token)
        logger.info("登录成功，已保存访问令牌")

        # 返回响应对象供调用方查看
        return response

    # ------------------------------------------------------------------
    # 3.6 资源释放
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭会话，释放连接池中占用的连接。"""
        self.session.close()

    def __enter__(self) -> "HttpClient":
        """支持 with 语句，进入上下文时返回自身。"""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """支持 with 语句，退出上下文时自动关闭会话。

        无论 with 块内是正常结束还是抛出异常，都会执行关闭动作，
        避免连接泄漏。
        """
        self.close()


if __name__ == "__main__":
    # 自检：跑一遍健康检查，验证客户端可用
    with HttpClient(base_url="http://localhost:8000", timeout=5) as client:
        try:
            resp = client.get("/api/v1/health", expect_status=200)
            print("健康检查通过:", resp.json())
        except HttpError as error:
            print("健康检查失败:", error)
