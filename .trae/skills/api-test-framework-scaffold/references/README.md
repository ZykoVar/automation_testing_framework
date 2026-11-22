# 参照基准副本 · day10

本目录是 day10 接口自动化测试框架的**完整源文件副本**，作为
`api-test-framework-scaffold` 技能的参照基准。

生成新框架时以本目录为模板：逐文件对齐目录层级、文件名、模块划分、
类名与函数名、fixture 名称、导入写法、日志格式、注释风格，
只把被【】占位符覆盖的取值换掉。

## 与真实 day10 目录的差异

| 项 | 差异 | 原因 |
|---|---|---|
| `.env` → `.env.template` | 文件名改了，密钥脱敏为 `sk-xxxxxx请替换为你的真实密钥xxxxxx` | 本目录要提交到版本库，不能带真实密钥 |
| `report/` | 未包含 | Allure 报告产物，每次执行重新生成 |
| `ai_debug_reports/` | 未包含 | AI 排错报告产物，每次执行重新生成 |
| `__pycache__/` | 未包含 | Python 字节码缓存 |
| `.pytest_cache/` | 未包含 | pytest 缓存 |

## 目录清单

```
day10/
├── .env.template               # 大模型配置模板（复制为 .env 后填密钥）
├── .gitignore                  # 必须包含 .env
├── __init__.py                 # 使项目目录本身成为一个包
├── pytest.ini                  # markers 注册 + testpaths
├── cli.py                      # 入口脚本，转发 pytest 参数
├── conftest.py                 # 根 conftest：session 级 fixture + AI 排错钩子
├── utils/
│   ├── __init__.py             # 包说明，含模块清单与依赖方向
│   ├── AI_HttpClient.py        # HTTP 客户端，类名 HttpClient
│   ├── config.py               # 共享配置与业务常量（多环境）
│   ├── yaml_loader.py          # YAML 用例加载器，含 ApiCase 数据类
│   ├── excel_loader.py         # Excel 用例加载器
│   ├── yaml_excel_generator.py # YAML 反向生成 Excel
│   ├── ai_prompts.py           # 提示词与公共片段，纯标准库
│   ├── ai_debug_helper.py      # 排错助手，含 call_llm 与 ai_debug
│   └── ai_assert.py            # 自然语言断言，含 ai_assert
├── data/
│   ├── excel_data/create_subject.xlsx
│   └── yaml_data/
│       ├── create_subject.yaml
│       └── login.yaml
└── test_case/
    ├── __init__.py
    ├── conftest.py             # 子目录 conftest：学生/学科数据工厂
    ├── test_login.py           # YAML 数据驱动
    ├── test_login_demo.py      # 传统断言 + AI 断言演示
    ├── test_demo_fail.py       # 故意失败用例，演示 AI 排错
    ├── test_student_flow.py    # 学生业务流程（Allure 装饰器 + step）
    └── test_subject_flow.py    # 学科业务流程 + Excel 数据驱动
```

## 复用时的取值替换清单

从本目录复制出 `dayXX` 后，只需替换以下位置：

| 文件 | 需替换的内容 |
|---|---|
| 全目录 | `day10` → `dayXX`（目录名、docstring、注释、路径推导） |
| `utils/config.py` | `ENVIRONMENTS` 里的 `BASE_URL`、`API_USERNAME` / `API_PASSWORD` 的默认值、接口路径常量 |
| `utils/yaml_loader.py` | `DEFAULT_VARIABLES` 里的 `BASE_URL` |
| `utils/AI_HttpClient.py` | docstring 与 `__main__` 示例里的地址 |
| `utils/ai_prompts.py` | `__main__` 示例里的地址 |
| `utils/ai_debug_helper.py` | 本地规则里 `HTTPConnectionPool` 的端口号 |
| `data/yaml_data/*.yaml` | `base_url: ${BASE_URL}`（占位符会由加载期渲染，无需改） |
| `test_case/*.py` | `from day10.utils...` 兜底导入里的包名 |

## 复制时必须一起带走的三个坑

这三点在 day10 调试阶段各花掉一轮排查，复制基准时不要改回去：

**1. 账号配置键必须带 `API_` 前缀**

Windows 系统自带 `USERNAME` 环境变量（值为当前登录用户，如 `DELL`）。
`get_config("USERNAME", "admin")` 会优先读到它，于是拿系统用户名去登录，
服务端一律返回 401，所有需要鉴权的用例全灭 —— 但报错信息是
「用户名或密码错误」，完全看不出是配置被污染了。

所以基准里用的是 `API_USERNAME` / `API_PASSWORD`，
且 `get_config` 里有 `SYSTEM_ENV_BLOCKLIST` 黑名单兜底。

**2. 占位符替换只能替「值恰好等于占位符」的字段**

`test_subject_flow.py` 的 `_replace_subject_code()` 判断条件是
`case.json_body.get("code") == "${SUBJECT_CODE}"`，而不是「存在 code 字段就替换」。
异常用例（编码超过二十个字符）故意写死了 26 个字符，
一旦被替换成唯一编码，校验场景就没了，用例会从「期望 422」变成「实际 201」。

**3. 「删除成功」要在 cleanup 之前断言**

`factory.cleanup()` 是兜底清理，调用后数据已经没了。
用例里必须先 DELETE 断言「已删除」，再查一次断言「不存在」，
最后才交给 teardown 的 cleanup 兜底。
顺序反了就永远验证不到删除成功的正常路径。

**4. 数据驱动的创建类用例要自带清理**

`test_create_subject_from_excel` 不走工厂夹具，工厂的 cleanup 管不到它。
若不在用例末尾从响应里取 `data.id` 再删一次，
每次执行都会在库里留下一条「自动化测试学科」，跑得越多积得越多。

```python
created_id = (body.get("data") or {}).get("id")
if created_id:
    auth_http_client.delete("{}{}".format(SUBJECTS_PATH, created_id), expect_status=None)
```

异常用例服务端已回滚，取不到 id 就跳过，天然兼容。

## 依赖

```
pytest
requests
allure-pytest
openpyxl
PyYAML
```

安装：

```powershell
pip install pytest requests allure-pytest openpyxl PyYAML
```

## 基准自身的验证状态

- `python -m pytest test_case -m "not demo_fail"` → 47 passed
- `python -m pytest test_case` → 49 项中 47 通过，2 条 `demo_fail` 按设计失败
  并在 `ai_debug_reports/` 产出诊断报告
- 被测服务：EduScore AI 学生成绩系统，`http://localhost:8000`

