import json
import os
import uuid
from typing import List, Dict, Any, Union

import pandas as pd
from loguru import logger

from HAT.core.global_context import GlobalContext


def load_database_configuration(sheet_name: str, db_info: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    加载数据库配置信息
    
    从Excel的database_configuration工作表中读取数据库配置信息，
    并将其转换为以别名为键的字典格式。
    
    Args:
        sheet_name: 工作表名称
        db_info: 包含数据库配置信息的DataFrame
        
    Returns:
        数据库配置字典，格式为: {alias: {host, port, user, password, db}}
    """
    logger.debug(f"加载数据库配置: {sheet_name}")
    db_config = db_info.fillna("").to_dict(orient="records")

    config_dict = {}
    for item in db_config:
        alias = item.get("alias")
        host = item.get("host")
        port = item.get("port")
        user = item.get("user")
        password = item.get("password")
        db = item.get("db")

        db_info_dict = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "db": db,
        }
        config_dict[alias] = db_info_dict
    return config_dict


def load_general_configuration(sheet_name: str, general_info: pd.DataFrame) -> Dict[str, Any]:
    """
    加载通用配置信息
    
    从Excel的general_configuration工作表中读取通用配置信息，
    并尝试将字符串格式的JSON转换为字典对象。
    
    Args:
        sheet_name: 工作表名称
        general_info: 包含通用配置信息的DataFrame
        
    Returns:
        通用配置字典
    """
    logger.debug(f"加载通用配置: {sheet_name}")
    config_dict = {row["configuration_name"]: row["configuration_value"] for _, row in general_info.iterrows()}

    def to_dict(input_value: Union[str, dict, Any]) -> Union[dict, Any]:
        """
        尝试将字符串转换为字典对象
        
        Args:
            input_value: 待转换的值
            
        Returns:
            转换后的字典或原始值
        """
        if isinstance(input_value, dict):
            return input_value
        elif isinstance(input_value, str):
            try:
                return json.loads(input_value)
            except json.JSONDecodeError:
                return input_value
        else:
            return input_value

    for key, value in config_dict.items():
        config_dict[key] = to_dict(value)
    return config_dict


def load_context_from_excel(file_path: str) -> None:
    """
    从Excel文件加载上下文配置
    
    在指定目录中查找context.xlsx文件，如果存在则加载其中的配置信息
    并将其设置到全局上下文中。
    
    Args:
        file_path: 包含context.xlsx文件的目录路径
    """
    try:
        excel_file_path = os.path.join(file_path, "context.xlsx")
        # 检查文件是否存在
        if not os.path.exists(excel_file_path):
            logger.debug(f"上下文配置文件不存在: {excel_file_path}")
            return

        context_data = {}

        # 读取数据库配置
        database_configuration_sheet = pd.read_excel(excel_file_path, sheet_name="database_configuration")
        database_configuration = load_database_configuration("database_configuration", database_configuration_sheet)
        context_data.update({"_database": database_configuration})

        # 读取通用配置
        general_configuration_sheet = pd.read_excel(excel_file_path, sheet_name="general_configuration")
        general_configuration = load_general_configuration("general_configuration", general_configuration_sheet)
        context_data.update(general_configuration)

        # 将配置信息设置到全局上下文中
        if context_data:
            GlobalContext().set_by_dict(context_data)
            logger.debug(f"成功加载Excel上下文配置: {excel_file_path}")
    except Exception as e:
        error_msg = f"加载Excel上下文配置失败 {file_path}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)


def group_cases_by_title(test_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按标题对测试用例进行分组
    
    将从Excel中读取的行数据按case_title进行分组，每一组构成一个完整的测试用例。
    
    Args:
        test_data: 从Excel中读取的测试数据列表
        
    Returns:
        分组后的测试用例列表
    """
    result = []
    current_case = None

    for row in test_data:
        case_title = row.get("case_title")
        module = row.get("module")
        function = row.get("function")
        case_type = row.get("case_type")
        # 如果当前行没有指定case_type，则使用全局配置中的case_type
        if case_type is None:
            case_type = GlobalContext().get_context("case_type")
        case_steps = row.get("case_steps")
        request_method = row.get("request_method")
        request_data = row.get("request_data")

        # 解析请求数据为字典格式
        request_data_dict = {}
        # 确保request_data是字符串类型且不为空
        if request_data is not None and isinstance(request_data, str) and request_data.strip() != "":
            try:
                json_data = json.loads(request_data)
                # 过滤掉值为"nan"的字段
                request_data_dict = {k: v for k, v in json_data.items() if v != "nan"}
            except Exception as e:
                logger.warning(f"解析JSON数据失败: {e}")

        # 如果遇到新的用例标题，则开始一个新的用例
        if case_title is not None and case_title != "" and not pd.isna(case_title):
            if current_case is not None:
                result.append(current_case)
            # 初始化新的测试用例结构
            current_case = {"basic_configuration": {}, "case_steps": []}
            current_case["basic_configuration"].update({
                "case_type": case_type,
                "case_title": case_title,
                "module": module,
                "function": function,
            })

        # 将当前行的步骤信息添加到当前用例中
        if current_case is not None:
            current_case["case_steps"].append({case_steps: {
                "request_method": request_method,
                **request_data_dict
            }})

    # 添加最后一个用例
    if current_case is not None:
        result.append(current_case)
    return result


def load_excel_files(file_path: str) -> List[Dict[str, Any]]:
    """
    加载目录中的所有Excel测试用例文件
    
    该函数会按数字顺序加载指定目录中的所有Excel文件，并同时加载上下文配置。
    文件命名格式应为: 数字_描述.xlsx (例如: 1_login.xlsx)
    
    Args:
        file_path: 包含Excel文件的目录路径
        
    Returns:
        Excel测试用例信息列表
    """
    excel_case_infos = []
    load_context_from_excel(file_path)

    # 获取所有以数字开头的Excel文件并按数字排序
    file_names = [(int(f.split("_")[0]), f) for f in os.listdir(file_path)
                  if f.endswith(".xlsx") and f.split("_")[0].isdigit()]
    file_names.sort()
    sorted_file_names = [f[-1] for f in file_names]

    # 依次加载每个Excel文件
    for file_name in sorted_file_names:
        full_file_path = os.path.join(file_path, file_name)
        try:
            # 读取Excel文件的第一个工作表
            test_data = pd.read_excel(full_file_path, sheet_name=0)
            # 将NaN值替换为None
            test_data.where(test_data.notnull(), None)
            test_data = test_data.to_dict(orient="records")
            # 按标题对测试用例进行分组
            grouped_cases = group_cases_by_title(test_data)
            # 将分组后的用例添加到结果列表中
            for case in grouped_cases:
                excel_case_infos.append(case)
            logger.debug(f"成功加载Excel测试用例文件: {full_file_path}")
        except Exception as e:
            logger.error(f"加载Excel测试用例文件失败 {full_file_path}: {e}")
            raise

    return excel_case_infos


def excel_case_parser(file_path: str) -> Dict[str, List]:
    """
    解析Excel格式的测试用例
    
    解析指定目录中的所有Excel测试用例文件。
    
    Args:
        file_path: 包含Excel测试用例文件的目录路径
        
    Returns:
        包含测试用例信息和名称的字典，格式为:
        {
            "case_names": [用例名称列表],
            "case_infos": [用例信息列表]
        }
        
    Example:
        >>> excel_case_parser("./test_cases")
        {
            "case_names": ["test_login", "test_logout"],
            "case_infos": [{...}, {...}]
        }
    """
    case_infos = []
    case_names = []
    excel_case_infos = load_excel_files(file_path)

    # 提取用例名称和信息
    for case_info in excel_case_infos:
        case_name = case_info.get("basic_configuration", {}).get("case_title") \
                    or str(uuid.uuid4())
        case_names.append(case_name)
        case_infos.append(case_info)

    logger.debug(f"成功解析 {len(case_names)} 个Excel测试用例")
    return {
        "case_infos": case_infos,
        "case_names": case_names
    }
