"""
测试执行器模块

该模块定义了测试执行器类，负责执行解析后的测试用例，
包括前置脚本执行、测试步骤执行和后置脚本执行等完整流程。
"""

import copy
from typing import Any, Dict, List

import allure
from tqdm import tqdm

from HAT.context.api_case_context import ApiCaseContext
from HAT.context.web_case_context import WebCaseContext
from HAT.core.global_context import GlobalContext
from HAT.extend.script import run_script
from HAT.utils.step_log_collector import allure_step_with_log
from HAT.utils.var_render import refresh


class TestRunner:
    """
    测试执行器类
    
    负责执行单个测试用例的完整流程，包括：
    1. 初始化测试环境和关键字
    2. 执行前置脚本
    3. 逐个执行测试步骤
    4. 执行后置脚本
    """

    def test_case_execute(self, case_info: Dict[str, Any]) -> None:
        """
        执行单个测试用例
        
        Args:
            case_info: 测试用例信息字典，包含基本配置、步骤等信息
        """
        web_case_context = None
        try:
            # 获取测试用例基本配置
            basic_config = case_info.get("basic_configuration", {})

            # 根据用例类型初始化对应的关键字对象
            case_type = basic_config.get("case_type")
            if case_type == "ApiCase":
                keywords = ApiCaseContext().init_keywords()
            elif case_type == "WebCase":
                web_case_context = WebCaseContext()
                keywords = web_case_context.init_keywords()
            else:
                raise ValueError(f"Invalid case type: {case_type}")

            # 设置Allure报告相关属性
            allure.dynamic.parameter("case_info", None)
            allure.dynamic.feature(basic_config.get("module"))
            allure.dynamic.story(basic_config.get("function"))
            allure.dynamic.title(basic_config.get("case_title"))

            # 合并全局上下文和本地上下文
            local_context = case_info.get("local_context", {})
            context = copy.deepcopy(GlobalContext().show_context())
            context.update(local_context)

            # 执行前置脚本
            setup_script = refresh(case_info.get("setup_script", ""), context)
            if setup_script:
                try:
                    # 评估脚本字符串为Python对象并逐个执行
                    for script in eval(setup_script):
                        run_script.exec_script(script, GlobalContext().show_context())
                except Exception as e:
                    raise RuntimeError(f"执行前置脚本失败: {str(e)}")

            # 获取测试步骤
            case_steps: List[Dict[str, Any]] = case_info.get("case_steps", [])

            # 使用进度条执行测试步骤
            with tqdm(total=len(case_steps), desc="开始执行") as progress_bar:
                for step in case_steps:
                    # 获取步骤名称和值
                    step_name = list(step.keys())[0]
                    step_value = list(step.values())[0]

                    # 更新进度条描述和进度
                    progress_bar.set_description(f"{basic_config.get('case_title')}-current_step:{step_name}")
                    progress_bar.update(1)

                    # 刷新上下文并处理步骤值
                    context = copy.deepcopy(GlobalContext().show_context())
                    context.update(local_context)
                    try:
                        step_value = eval(refresh(step_value, context))
                    except Exception as e:
                        raise RuntimeError(f"处理步骤值失败: {str(e)}")

                    # 在Allure步骤中执行具体操作
                    with allure_step_with_log(step_name):
                        method = step_value["request_method"]
                        try:
                            # 尝试执行内置方法
                            request_method = keywords.__getattribute__(method)
                            request_method(**step_value)
                        except AttributeError:
                            # 如果内置方法不存在，尝试执行扩展方法
                            if GlobalContext().get_context("key_dir") is not None:
                                if keywords is not None:
                                    keywords.ex_invoke(request_method=method, step_value=step_value)
                                else:
                                    raise RuntimeError("Keywords not initialized, cannot invoke extension method")

            # 执行后置脚本
            context = copy.deepcopy(GlobalContext().show_context())
            context.update(local_context)

            teardown_script = refresh(case_info.get("teardown_script", ""), context)
            if teardown_script:
                try:
                    # 评估脚本字符串为Python对象并逐个执行
                    for script in eval(teardown_script):
                        run_script.exec_script(script, GlobalContext().show_context())
                except Exception as e:
                    raise RuntimeError(f"执行后置脚本失败: {str(e)}")
        finally:
            if web_case_context:
                web_case_context.release_driver()