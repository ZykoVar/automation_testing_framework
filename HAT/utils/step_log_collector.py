"""
步骤日志收集工具模块

该模块提供了在Allure测试报告中收集和展示步骤日志的功能。
通过捕获测试步骤执行过程中的日志信息，并将其作为附件添加到Allure报告中。
"""

import io
from contextlib import contextmanager
from typing import Any, Optional

import allure
from loguru import logger


class StepLogCollector:
    """
    步骤日志收集器类
    
    该类用于在特定的测试步骤中收集日志信息，并在步骤结束时将日志作为附件
    添加到Allure测试报告中。
    
    Attributes:
        log_buffer: 用于存储日志内容的内存缓冲区
        sink_id: Loguru日志处理器的ID，用于后续移除处理器
    """

    def __init__(self) -> None:
        """
        初始化步骤日志收集器
        """
        self.log_buffer: io.StringIO = io.StringIO()
        self.sink_id: Optional[int] = None

    def __enter__(self) -> 'StepLogCollector':
        """
        进入上下文管理器
        
        添加一个日志处理器，将日志内容写入内存缓冲区。
        
        Returns:
            StepLogCollector: 当前实例
        """
        self.sink_id = logger.add(self.log_buffer, level="DEBUG")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        退出上下文管理器
        
        移除日志处理器，获取缓冲区中的日志内容，并将其作为附件添加到Allure报告中。
        
        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常回溯信息
        """
        # 移除日志处理器
        if self.sink_id is not None:
            logger.remove(self.sink_id)
            
        # 获取日志内容
        log_content = self.log_buffer.getvalue()
        
        # 如果有日志内容，则添加到Allure报告中
        if log_content.strip():
            allure.attach(
                log_content,
                name="Step Log",
                attachment_type=allure.attachment_type.TEXT
            )
            
        # 关闭缓冲区
        self.log_buffer.close()


@contextmanager
def allure_step_with_log(step_name: str):
    """
    创建带日志收集功能的Allure测试步骤
    
    该上下文管理器结合了Allure的测试步骤和日志收集功能，
    可以在测试步骤执行过程中自动收集日志并添加到报告中。
    
    Args:
        step_name: 测试步骤的名称
        
    Example:
        >>> with allure_step_with_log("登录操作"):
        ...     # 执行登录相关操作
        ...     login(username, password)
    """
    # 创建Allure测试步骤
    with allure.step(step_name):
        # 在测试步骤中收集日志
        with StepLogCollector() as step_log_collector:
            yield step_log_collector
