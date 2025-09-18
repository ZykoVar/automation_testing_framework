"""
HAT测试框架主入口文件

该文件负责配置日志、设置pytest参数并运行测试，
同时生成Allure测试报告。
"""

import os
import sys
import time
from typing import List

import pytest
from allure_combine import combine_allure
from loguru import logger

from HAT.core.cases_plugin import CasesPlugin


def setup_logging() -> str:
    """
    配置日志系统
    
    Returns:
        str: 格式化后的时间字符串，用于日志文件命名
    """
    time_str = time.strftime("%Y%m%d%H%M%S", time.localtime())
    log_level = os.getenv("HAT_LOG_LEVEL", "DEBUG").upper()

    # 移除默认的日志处理器并添加自定义处理器
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    logger.add(os.path.join("./HAT/logs", f"{time_str}.log"), level=log_level)
    
    return time_str


def get_pytest_args() -> List[str]:
    """
    获取pytest命令行参数
    
    Returns:
        List[str]: pytest参数列表
    """
    # 优先从环境变量获取配置
    # cases_type = "excel"
    # cases_path = "./examples/api_cases_excel"
    cases_type = "yaml"
    cases_path = "./examples/api_cases_yaml"
    
    args = [
        "-v",  # 详细模式，显示每个测试用例的详细信息
        "-s",  # 允许输出print语句的内容，不捕获标准输出
        "--capture=sys",  # 指定捕获策略为sys，控制输出行为
        "--alluredir=allure-results",  # 指定allure测试结果的输出目录
        "--clean-alluredir",  # 清理allure结果目录
        "--tb=short",  # 显示简洁的错误追踪信息
        "--reruns", "2",
        "--reruns-delay", "1",
        "./HAT/core/test_runner.py",  # 指定测试运行器
        f"--cases_type={cases_type}",  # 指定用例类型
        f"--cases_path={cases_path}"  # 指定用例路径
    ]
    
    return args


def generate_allure_report() -> None:
    """
    生成Allure测试报告
    """
    # 生成allure报告
    exit_code = os.system("allure generate allure-results -o allure-report --clean")
    if exit_code != 0:
        logger.warning("Allure报告生成可能存在问题")
    
    # 合并allure报告
    try:
        combine_allure("./allure-report")
    except Exception as e:
        logger.warning(f"合并Allure报告时出错: {e}")


def main() -> None:
    """
    主函数：运行测试并生成报告
    """
    # 设置日志
    time_str = setup_logging()
    logger.info(f"开始执行测试，日志文件: ./HAT/logs/{time_str}.log")
    
    # 获取测试参数
    pytest_args = get_pytest_args()
    logger.info(f"测试参数: {pytest_args}")
    
    # 运行测试
    logger.info("开始运行测试用例...")
    exit_code = pytest.main(pytest_args, plugins=[CasesPlugin()])
    logger.info(f"测试执行完成，退出码: {exit_code}")
    
    # 生成报告
    logger.info("开始生成Allure测试报告...")
    generate_allure_report()
    logger.info("Allure测试报告生成完成")


if __name__ == '__main__':
    main()
