"""
测试用例解析器模块

该模块提供统一的测试用例解析接口，根据用例类型调用相应的解析器
来处理不同格式的测试用例文件（如YAML、Excel等）。
"""

import os.path
from typing import Dict, List

from loguru import logger

from HAT.parse.excel_case_parser import excel_case_parser
from HAT.parse.yaml_case_parser import yaml_case_parser

# 定义支持的用例类型映射
CASE_PARSERS = {
    "yaml": yaml_case_parser,
    "excel": excel_case_parser
}


def case_parser(case_type: str, case_dir: str) -> Dict[str, List]:
    """
    根据用例类型解析测试用例
    
    该函数是一个统一入口，根据传入的用例类型参数，
    调用对应的解析器来处理测试用例文件。
    
    Args:
        case_type (str): 用例类型，如"yaml"或"excel"
        case_dir (str): 用例文件所在的目录路径
        
    Returns:
        dict: 包含解析后的测试用例信息的字典
              格式为: {
                  "case_names": [用例名称列表],
                  "case_infos": [用例信息列表]
              }
              
    Raises:
        ValueError: 当不支持的用例类型传入时
        FileNotFoundError: 当指定的用例目录不存在时
              
    Example:
        >>> case_parser("yaml", "./test_cases")
        {
            "case_names": ["test_login", "test_logout"],
            "case_infos": [{...}, {...}]
        }
    """
    # 检查用例目录是否存在
    if not os.path.exists(case_dir):
        raise FileNotFoundError(f"用例目录不存在: {case_dir}")

    # 将相对路径转换为绝对路径
    case_path = os.path.abspath(case_dir)

    # 记录日志，显示正在加载测试用例
    logger.debug(f"正在加载测试用例: {case_path}")

    # 检查是否支持该用例类型
    if case_type not in CASE_PARSERS:
        supported_types = ", ".join(CASE_PARSERS.keys())
        logger.warning(f"不支持的用例类型: {case_type}，支持的类型包括: {supported_types}")
        # 返回空的用例数据结构
        return {
            "case_names": [],
            "case_infos": []
        }

    try:
        # 根据用例类型调用相应的解析器
        parser_func = CASE_PARSERS[case_type]
        parsed_data = parser_func(case_path)

        # 验证返回数据格式
        if not isinstance(parsed_data, dict):
            raise ValueError("解析器返回的数据格式不正确，应为字典类型")

        if "case_names" not in parsed_data or "case_infos" not in parsed_data:
            raise ValueError("解析器返回的数据缺少必要的键: case_names 或 case_infos")

        logger.debug(f"成功解析 {len(parsed_data['case_names'])} 个测试用例")
        return parsed_data

    except Exception as e:
        logger.error(f"解析测试用例时发生错误: {str(e)}")
        # 发生错误时返回空的用例数据结构
        return {
            "case_names": [],
            "case_infos": []
        }
