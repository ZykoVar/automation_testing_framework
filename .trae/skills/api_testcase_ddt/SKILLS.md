# SKILLS.md · 单接口 YAML 驱动异常用例（最小侵入）

用法：填好下面「接口信息」，连同本文件交给 AI，即生成 3 个新文件。已有文件零改动。

---

## 1. 接口信息（复制填写，缺项填「未知」）

```
接口标识(英文)：            # 例：login、create_order —— 决定文件名与 case_id 前缀
接口中文名/模块：           # 例：用户登录 / 登录模块
Method + Path：             # 例：POST /api/v1/login
请求体形态：                # json_body / params / data / files  四选一
必填字段(名:类型:合法值)：   # 例：username:str:admin, password:str:admin123
选填字段：
公共 headers / 鉴权方式：    # 例：Content-Type:application/json；无 token / conftest 有 token fixture
base_url：                  # 例：http://127.0.0.1:8080（或从 conftest 的 base_url 取）
正常用例期望：              # 状态码 + message + 关键返回字段
异常输入期望：              # 各类非法输入分别返回什么状态码与 message ← 各项目差异最大，必须给
提示字段名：                # message / msg / error / detail
有枚举的字段(合法值集合)：   # 用于构造「非法枚举值」用例
有边界的字段(长度/数值区间)：# 用于构造「超长字符串 / 越界数值」用例
可用 fixture 名：           # conftest 里确实存在的，如 base_url、token；不确定写「未知」
```

---

## 2. 硬约束

1. 只新增文件，不改任何已有文件（含 conftest.py、pytest.ini、cli.py、__init__.py）。
2. 新文件只落在 `data/yaml_data/`、`untils/`、`test_case/`，不新建目录。
3. 测试文件名 `test_{接口标识}.py`，沿用 pytest.ini 现有收集规则。
4. 只用 conftest 里已存在的 fixture，不新建 fixture / 命令行参数。
5. 只做单个接口，不做分组、重构、allure、cli 改造。
6. 路径用 `Path(__file__).resolve().parent.parent` 推导，禁止绝对路径。

---

## 3. 产出三个文件

| 文件 | 内容要点 |
|---|---|
| `data/yaml_data/{接口标识}.yaml` | 文件级 `module/interface/name/method/path/headers` + `cases` 列表；1 条正常 + **≥8 条异常**（必填缺失、空串、null、类型错误、多余传参、超长、越界、非法枚举、SQL/特殊字符注入、错误 Content-Type、重复提交）。用例字段：`case_id`(接口名+三位序号)、`case_name`、`story`、请求体、`expect_status`、`expect_message`、`expect_json`、`skip` |
| `untils/yaml_loader.py` | 通用件，不随接口变，已存在则复用不重写。含 `load_yaml_file`(错误带文件名)、`render_vars`(${VAR} 替换)、`parse_file`(文件级配置下沉、用例级覆盖)、`load_cases`(按 case_id 过滤)、`ApiCase` dataclass(`to_request_kwargs()` / `pytest_id`)。加载期校验 case_id 重复、必填缺失、method 非法、expect_status 缺失，报错带文件名+第几条 |
| `test_case/test_{接口标识}.py` | 导入 `from untils.yaml_loader import load_cases`（含 sys.path 兼容兜底）；`@pytest.mark.parametrize("case", CASES, ids=lambda c: c.pytest_id)` 一个函数跑完全部用例；本文件内定 base_url 与 requests 调用；断言状态码 + message + expect_json；失败信息带 case_id / case_name / 请求参数 / 实际响应；请求异常转 `pytest.fail` 不影响其他用例 |

---

## 4. 验收

只新增 3 个文件 · `pytest --collect-only` 能收集 · ids 形如 `login002-失败-账号不存在` · 异常场景 ≥8 类全覆盖 · 无绝对路径 · 手工改错一条 `expect_status` 验证其失败且不影响其他用例。

---

## 5. 调用指令

```
按 SKILLS.md，为接口【create_subject】新增 YAML 驱动异常用例，接口信息如下：
http://localhost:8000/docs   只要接口文档中的新增学科接口信息
只新增 data/yaml_data/{create_subject}.yaml、untils/yaml_loader.py、test_case/test_{create_subject}.py，
不改任何已有文件与 pytest.ini，异常用例 2 条。
```
