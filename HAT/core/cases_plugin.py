"""
测试用例插件模块

该模块定义了一个pytest插件，用于处理不同类型的测试用例，
包括解析用例、参数化测试和处理关键字扩展。
"""

from typing import Any, List

from HAT.core.global_context import GlobalContext
from HAT.parse.case_parser import case_parser


class CasesPlugin:
    """
    HAT测试框架的pytest插件类
    
    该类实现了pytest的钩子函数，用于：
    1. 添加命令行选项
    2. 生成测试参数
    3. 修改测试项的显示名称
    """
    @staticmethod
    def pytest_addoption(parser) -> None:
        """
        添加自定义命令行选项
        
        Args:
            parser: pytest的参数解析器对象
        """
        # 添加用例类型选项（如excel、yaml等）
        parser.addoption(
            "--cases_type",
            action="store",
            default="yaml",
            help="测试用例类型，如excel、yaml等"
        )
        # 添加用例路径选项
        parser.addoption(
            "--cases_path",
            action="store",
            default="./examples/api_cases_yaml",
            help="测试用例文件路径"
        )
        # 添加关键字扩展目录选项
        parser.addoption(
            "--key_dir",
            action="store",
            default=None,
            help="扩展关键字目录"
        )
    @staticmethod
    def pytest_generate_tests(metafunc) -> None:
        """
        生成测试函数的参数化数据
        
        Args:
            metafunc: pytest的元函数对象，包含测试函数的相关信息
        """
        # 从命令行参数中获取配置
        cases_type = metafunc.config.getoption("cases_type")
        cases_path = metafunc.config.getoption("cases_path")
        key_dir = metafunc.config.getoption("key_dir")

        # 将key_dir设置到全局上下文中
        GlobalContext().set_context("key_dir", key_dir)

        try:
            # 解析测试用例数据
            data = case_parser(cases_type, cases_path)
        except Exception as e:
            raise RuntimeError(f"解析测试用例失败: 类型={cases_type}, 路径={cases_path}, 错误={str(e)}")

        # 如果测试函数需要case_info参数，则进行参数化
        if "case_info" in metafunc.fixturenames:
            # 检查数据完整性
            if "case_infos" not in data or "case_names" not in data:
                raise ValueError("解析的测试用例数据格式不正确，缺少必要的键")

            # 使用解析得到的用例信息和用例名称进行参数化
            metafunc.parametrize(
                "case_info",
                data["case_infos"],
                ids=data["case_names"]
            )
    @staticmethod
    def pytest_collection_modifyitems(items: List[Any]) -> None:
        """
        修改测试项集合，处理测试项的名称编码
        
        Args:
            items: 测试项列表
        """
        # 遍历所有测试项，处理名称的Unicode转义
        for item in items:
            try:
                # 处理测试项名称的编码
                item.name = item.name.encode("utf-8").decode("unicode_escape")
                # 处理测试项节点ID的编码
                item._nodeid = item.nodeid.encode("utf-8").decode("unicode_escape")
            except Exception as e:
                # 如果编码处理失败，保留原始值并记录警告
                print(f"警告: 处理测试项编码时出错 {item.name}: {str(e)}")
