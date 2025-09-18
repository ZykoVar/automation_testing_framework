"""
YAML测试用例解析模块

该模块提供了解析YAML格式测试用例的功能，支持基础用例和数据驱动测试(DDT)用例的解析。
"""

import copy
import os
import uuid
from typing import List, Dict, Any

import yaml
from loguru import logger

from HAT.core.global_context import GlobalContext


def read_yaml(file_path: str) -> List[Dict[str, Any]]:
    """
    读取单个YAML文件
    
    Args:
        file_path: YAML文件路径
        
    Returns:
        包含YAML数据的列表
        
    Raises:
        Exception: 当文件读取或解析失败时抛出异常
    """
    case_infos = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.full_load(f)
            case_infos.append(data)
        return case_infos
    except Exception as e:
        logger.error(f"读取YAML文件失败 {file_path}: {e}")
        raise


def load_context_from_yaml(file_path: str) -> None:
    """
    从YAML文件加载上下文配置
    
    在指定目录中查找context.yaml文件，如果存在则加载其中的配置信息
    并将其设置到全局上下文中。
    
    Args:
        file_path: 包含context.yaml文件的目录路径
    """
    context_file_path = os.path.join(file_path, "context.yaml")
    try:
        if os.path.exists(context_file_path):
            with open(context_file_path, "r", encoding="utf-8") as f:
                context = yaml.load(f, Loader=yaml.FullLoader)
                if context:
                    GlobalContext().set_by_dict(context)
                    logger.debug(f"成功加载上下文配置: {context_file_path}")
    except Exception as e:
        error_msg = f"加载上下文配置失败 {context_file_path}: {e}"
        logger.error(error_msg)
        raise Exception(error_msg)


def load_yaml_files(file_path: str) -> List[Dict[str, Any]]:
    """
    加载目录中的所有YAML测试用例文件
    
    该函数会按数字顺序加载指定目录中的所有YAML文件，并同时加载上下文配置。
    文件命名格式应为: 数字_描述.yaml (例如: 1_login.yaml)
    
    Args:
        file_path: 包含YAML文件的目录路径
        
    Returns:
        YAML测试用例信息列表
    """
    yaml_case_infos = []
    load_context_from_yaml(file_path)

    # 获取所有以数字开头的YAML文件并按数字排序
    file_names = [(int(f.split("_")[0]), f) for f in os.listdir(file_path)
                  if f.endswith(".yaml") and f.split("_")[0].isdigit()]
    file_names.sort()
    sorted_file_names = [f[-1] for f in file_names]

    for file_name in sorted_file_names:
        full_file_path = os.path.join(file_path, file_name)
        try:
            with open(full_file_path, "r", encoding="utf-8") as f:
                case_info = yaml.full_load(f)
                if case_info:
                    yaml_case_infos.append(case_info)
            logger.debug(f"成功加载测试用例文件: {full_file_path}")
        except Exception as e:
            logger.error(f"加载测试用例文件失败 {full_file_path}: {e}")
            raise

    return yaml_case_infos


def yaml_case_parser(file_path: str) -> Dict[str, List]:
    """
    解析YAML格式的测试用例
    
    解析指定目录中的所有YAML测试用例文件，支持普通用例和数据驱动测试(DDT)用例。
    对于DDT用例，会为每个数据集生成一个独立的测试用例。
    
    Args:
        file_path: 包含YAML测试用例文件的目录路径
        
    Returns:
        包含测试用例信息和名称的字典，格式为:
        {
            "case_names": [用例名称列表],
            "case_infos": [用例信息列表]
        }
        
    Example:
        >>> yaml_case_parser("./test_cases")
        {
            "case_names": ["test_login", "test_logout"],
            "case_infos": [{...}, {...}]
        }
    """
    case_infos = []
    case_names = []
    yaml_case_infos = load_yaml_files(file_path)

    # 遍历所有YAML测试用例
    for case_info in yaml_case_infos:
        # 获取数据驱动测试数据(DDT)
        ddts = case_info.get("ddt", [])
        # 如果存在ddt数据，则移除原始ddt键
        if ddts:
            case_info.pop("ddt")

        # 处理没有ddt的普通用例
        if not ddts:
            case_name = case_info.get("basic_configuration", {}).get("case_title") \
                        or str(uuid.uuid4())
            case_names.append(case_name)
            case_infos.append(case_info)
        else:
            # 处理带ddt的数据驱动测试用例，为每个ddt数据生成一个测试用例
            basic_config = case_info.get("basic_configuration", {})
            base_case_name = basic_config.get("case_title") or str(uuid.uuid4())

            for ddt in ddts:
                # 深拷贝原始用例信息，确保每个用例独立
                new_case = copy.deepcopy(case_info)
                # 将当前DDT数据添加到新用例的本地上下文中
                new_case.update({"local_context": ddt})

                # 生成用例名称，格式为: 基础用例名-场景名
                scenario_title = ddt.get("scenario_title") or str(uuid.uuid4())
                case_name = f"{base_case_name}-{scenario_title}"

                # 更新新用例的标题
                if "basic_configuration" not in new_case:
                    new_case["basic_configuration"] = {}
                new_case["basic_configuration"]["case_title"] = case_name

                case_infos.append(new_case)
                case_names.append(case_name)

    logger.debug(f"成功解析 {len(case_names)} 个YAML测试用例")
    return {
        "case_infos": case_infos,
        "case_names": case_names
    }
