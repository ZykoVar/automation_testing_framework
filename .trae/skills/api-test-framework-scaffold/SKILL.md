---
name: api-test-framework-scaffold
description: Generate a complete enterprise-grade interface API automation test framework from a scaffolding prompt, producing the directory tree, layered utils (HTTP client, config, YAML/Excel loaders, AI debug + AI assert), session fixtures, data-driven test cases, Allure reporting and CLI entry. Use when the user asks for 接口自动化框架, 自动化测试框架脚手架, API 自动化框架生成, pytest 框架初始化, or supplies a prompt containing 【参照基准】/【硬性要求】/【项目信息】. Not for designing a single test case list.
---

# 接口自动化测试框架脚手架生成器

按固定目录结构生成一套可直接运行的接口自动化测试框架。所有可调项以 `【】` 标记，
**生成前必须逐项向用户确认是否替换**，用户给了新值就用新值，用户说不换就用默认值。

---

## 1. 交互协议（强制，不可跳过）

### 1.1 提取占位符

从用户提示词中提取全部 `【...】` 占位符。没有 `【】` 标记时，直接用第 3 节的默认值。

### 1.2 一次性列出，逐项询问

用 `AskUserQuestion` 一次性把占位符列出来让用户决定，**不要逐个来回问**。
每个问题给 2–4 个选项，第一个选项是「保持默认：<默认值>」，用户也可以直接输入新值。

| 占位符 | 默认值 | 说明 |
|---|---|---|
| `【项目目录名】` | `day10` | 框架根目录名，所有相对路径与文档字符串都跟着变 |
| `【base_url】` | `http://localhost:8000` | 被测服务地址，写进 `utils/config.py` |
| `【接口前缀】` | `/api/v1` | 拼在所有接口路径前 |
| `【账号密码】` | `admin / admin123` | 拆成 `USERNAME` / `PASSWORD` 两个常量 |
| `【核心接口】` | `登录接口、创建学生接口、查询学生接口、删除学生接口` | 决定生成哪几条业务流程用例 |
| `【异常场景】` | `登录失败、创建学生失败、查询学生失败、删除学生失败、学生不存在` | 决定异常用例覆盖清单 |
| `【参照基准】` | `references/day10`（本技能自带，见第 2 节） | 逐文件对齐的来源目录 |

**取值规则（必须严格遵守）：**

- 用户给了新值 → 用新值，替换掉默认值，且**代码里不得残留默认值**（包括注释、docstring、自检脚本里的示例地址）。
- 用户说「不换 / 用默认 / 就这样」 → 用默认值，不做任何改动。
- 用户没提到某个占位符 → 用默认值。
- 用户直接给了完整提示词且没提出异议 → 仍需就占位符问一次，不要自作主张跳过。

### 1.3 生成方式

**优先走「复制基准 + 替换取值」**，不要对着第 3、4 节逐字重写：

1. 复制 `references/day10/` 整个目录，改名为 `【项目目录名】`。
2. 按 `references/README.md` 的「取值替换清单」逐项替换 —— 目录名、base_url、
   接口前缀、账号密码、核心接口、异常场景。
3. `.env.template` 复制为 `.env`，填入真实密钥（不要提交）。
4. 按第 3 节核对目录树是否齐全（第 4 节新增的模块按需补）。
5. 按第 6 节跑自检清单。

只有当用户要求的结构与基准差异很大（换语言、换框架、换目录组织）时，才按第 4 节从零写。

### 1.4 环境自检（生成前必做）

生成代码前先确认被测服务在跑，避免生成完才发现端口不通：

```powershell
python -c "import socket;s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',8000));print('OPEN')"
```

- 端口不通 → 用 `base_url` 的默认值去试一次；仍不通则在交付说明里写清
  「配置层支持 `$env:BASE_URL` 覆盖，切换服务地址不需要改代码」。

---

## 2. 参照基准的逐文件对齐规则

参照基准是上一版框架目录。**默认基准就在本技能的 `references/` 下**：

```
references/
├── README.md          # 基准说明、目录清单、取值替换清单、依赖
└── day10/             # day10 完整源文件副本（25 个文件，目录结构与线上一致）
```

`references/day10/` 即标准参照基准。生成新框架时**优先直接复制这个目录**，
再按下表替换取值，比对着 SKILL.md 逐字重写更快也更不容易漏项。

需要用别的目录当基准时（如用户指定 day8），按同样的 8 个维度对齐即可。

**对齐以下 8 个维度，缺一不可**：

| 维度 | 对齐含义 |
|---|---|
| 目录层级 | 每个子目录的位置与职责不变（`utils/` `data/` `test_case/` `ai_debug_reports/` `report/`） |
| 文件名 | 文件名一字不改，包括 `AI_HttpClient.py` 这类大写下划线写法 |
| 模块划分 | 一个文件只干一件事；`ai_prompts` 纯标准库，不 import 任何项目内模块 |
| 类名与函数名 | `HttpClient` / `ApiCase` / `ai_assert` / `call_llm` / `ai_debug` 等命名保持一致 |
| fixture 名称 | `session_http_client` / `auth_http_client` / `student_factory` / `subject_factory` 不改名 |
| 导入写法 | `try: from utils.xxx import ... / except ImportError: from <项目>.utils.xxx import ...` 兜底 |
| 日志格式 | `"%(asctime)s [%(levelname)s] %(message)s"`，用 `logging` 不用 `print`（测试用例内可用 `print`） |
| 注释风格 | 模块头 docstring 说明「本文件做什么 + 依赖方向 + 怎么用」；每个函数 docstring 写 `:param:` `:return:` `:raises:`；行内注释写「为什么这么写」不写「这行在做什么」 |

**基准目录名 ≠ 新目录名时**，所有引用旧目录名的位置（import、docstring、注释、路径推导）都要改成新目录名。

---

## 3. 目录结构（硬性要求，逐文件产出）

```
【项目目录名】/
├── __init__.py                      # 使项目目录本身成为一个包
├── .env                             # 存 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
├── .gitignore                       # 必须包含 .env，禁止提交密钥
├── pytest.ini                       # 含 markers 注册与 testpaths
├── cli.py                           # 入口脚本，转发 pytest 参数
├── conftest.py                      # 根 conftest：session 级 fixture + AI 排错钩子
├── utils/                           # 工具层（注意是 utils，不是 untils）
│   ├── __init__.py                  # 包说明，含模块清单与依赖方向
│   ├── AI_HttpClient.py             # HTTP 客户端，类名 HttpClient
│   ├── config.py                    # 共享配置与业务常量
│   ├── yaml_loader.py               # YAML 用例加载器，含 ApiCase 数据类
│   ├── excel_loader.py              # Excel 用例加载器
│   ├── yaml_excel_generator.py      # YAML 反向生成 Excel
│   ├── ai_prompts.py                # 提示词与公共片段，纯标准库
│   ├── ai_debug_helper.py           # 排错助手，含 call_llm 与 ai_debug
│   └── ai_assert.py                 # 自然语言断言，含 ai_assert
├── data/
│   ├── yaml_data/                   # YAML 用例数据
│   │   └── login.yaml
│   └── excel_data/
│       └── create_subject.xlsx
├── test_case/                       # 测试脚本层
│   ├── __init__.py
│   ├── conftest.py                  # 子目录 conftest：数据工厂 fixture
│   ├── test_login.py                # YAML 数据驱动
│   ├── test_login_demo.py           # ai_assert 演示
│   ├── test_demo_fail.py            # 故意失败用例，演示 AI 排错
│   ├── test_student_flow.py         # 业务流程（Allure 装饰器 + step）
│   └── test_subject_flow.py
├── ai_debug_reports/                # AI 排错报告输出目录
└── report/                          # Allure 报告输出目录
```

---

## 4. 各文件职责与实现要点

### 4.1 `utils/config.py` — 共享配置

- 多环境：`ENVIRONMENTS` 字典，`ENV` 环境变量选环境，未识别退回 `dev`。
- 取值优先级：**环境变量 > .env > 代码默认值**，`get_config(key, default)` 统一封装。
- 代码里地址只出现一次：所有接口路径常量拼上 `API_PREFIX`。
- **配置键必须避开系统环境变量同名项**（Windows 上 `USERNAME`/`PASSWORD`/`HOME`/`PATH`
  都有系统值）。账号用 `API_USERNAME` / `API_PASSWORD`，
  并在 `get_config` 里加 `SYSTEM_ENV_BLOCKLIST` 黑名单兜底。
  否则 Windows 上 `USERNAME=DELL` 会被当成登录账号，所有需要鉴权的用例全部 401。
- 唯一学号/唯一学科代码生成函数：`generate_student_no()` / `generate_subject_no()`，
  组成是「前缀 + 毫秒时间戳 + 递增序号」，保证同一毫秒内多次调用也不重复。
- 导出目录常量：`YAML_DATA_DIR` / `EXCEL_DATA_DIR` / `AI_DEBUG_REPORT_DIR`。

### 4.2 `utils/AI_HttpClient.py` — HTTP 客户端

- 类名 `HttpClient`，异常 `HttpError`（携带原始 `response`，失败时仍能读响应体）。
- 基于 `requests.Session` 复用连接；挂 `urllib3.Retry`，`status_forcelist=[500,502,503,504]`，
  `raise_on_status=False`（重试耗尽后把响应正常返回，让上层能读响应体）。
- 核心方法签名：

  ```python
  def request(self, method, path, *, params=None, json_body=None, data=None,
              files=None, headers=None, timeout=None,
              expect_status=200, allow_redirects=True) -> requests.Response
  ```

- `login(path, payload, expect_status=200, token_field="access_token")` 保存令牌；
  `_merge_headers` 在有令牌时自动附加 `Authorization: Bearer <token>`。
- 便利方法 `get/post/put/delete/patch` 与 `get_json/post_json`。
- `close()` + `__enter__`/`__exit__` 支持 with 语法。

### 4.3 `utils/yaml_loader.py` — YAML 加载器

- `ApiCase` dataclass，字段：`case_id / case_name / story / method / path / base_url / headers /
  json_body / raw_body / params / expect_status / expect_message / expect_json / repeat / skip`，
  派生属性 `pytest_id`（`{case_id}-{case_name}`）。
- `render_vars(obj, variables)`：`${VAR}` 占位符替换，支持 dict/list/str 递归。
- `parse_file(path, variables)`：文件级字段下沉到每条用例，用例级覆盖文件级。
- `load_cases(path, variables)`：加载期校验 —— case_id 重复、必填缺失、method 非法，
  报错必须带**文件名 + 第几条**。
- `jsonpath_get(data, expression)`：迷你 JSONPath，支持 `$.a.b`、`$.a[0].b`。

### 4.4 `utils/excel_loader.py` / `utils/yaml_excel_generator.py`

- Excel 列顺序固定：`用例编号 | 用例名称 | 所属模块 | 请求方式 | 接口路径 | 请求头 | 请求体 | 期望状态码 | 期望响应文本 | 期望JSON字段`。
- `excel_loader` 复用 `yaml_loader` 的 `ApiCase` 与校验逻辑，保证 YAML/Excel 两条驱动产出完全一致。
- `yaml_excel_generator.generate_xlsx(yaml_path, output_path)` 反向生成 Excel，
  保留加粗表头、冻结首行、自动列宽。
- 两个文件都要能在「直接执行本文件」时工作：兜底 import 前把**项目目录（不是 utils 目录）**
  加进 `sys.path`。

### 4.5 `utils/ai_prompts.py` — 提示词（纯标准库）

- 不得 import 任何项目内模块，不 import requests。
- 常量：`ROLE_TEST_ENGINEER` / `ROLE_DEBUGGER` / `ROLE_JUDGE` / `ANALYSIS_STEPS` /
  `OUTPUT_FORMAT` / `DEBUG_PROMPT` / `ASSERT_PROMPT` / `RULE_PROMPT` / `REPORT_TEMPLATE`。
- `ASSERT_PROMPT` 必须要求模型**首行固定输出 `VERDICT: PASS` 或 `VERDICT: FAIL`**，
  靠关键词判断结论不稳定。
- 三个渲染函数：`render_debug_prompt` / `render_assert_prompt` / `render_rule_prompt`。

### 4.6 `utils/ai_debug_helper.py` — 排错助手

- `call_llm(prompt)`：项目里**唯一**一处大模型调用实现；未配置 API Key 时返回空串。
- `max_tokens` 给到 8192 —— 推理模型会用 `reasoning_content` 抢占 token，值太小正式回答会被截断。
- `build_debug_prompt(exception, request_info, response_text, code_snippet, context)`。
- `ai_debug(...)`：调大模型失败时降级到 `match_rule()` 本地规则引擎（五类：环境类/语法类/框架类/断言类/接口类）。
- `load_dotenv_config()` / `reload_config()` / `has_api_key()`。

### 4.7 `utils/ai_assert.py` — 自然语言断言

- `ai_assert(response, rule, strict=True, context="")`：
  - `strict=True` 不满足抛 `AssertionError`（走 pytest 失败 + AI 排错钩子）；
  - `strict=False` 只打印结论，不让用例失败（观察型）。
- 大模型不可用时降级到 `judge_by_local_rules` 正则规则表。
- `extract_payload` 必须把**状态码一起**送进提示词，否则模型会抱怨「缺少 HTTP 状态码」。
- 字段查找支持嵌套（`find_field_value` 递归），正则里引号设为可选。

### 4.8 `conftest.py`（根）— session 级 fixture + AI 排错钩子

- `session_http_client`（session 级、**始终未登录**，供鉴权失败类场景使用）。
- `auth_http_client`（session 级、独立实例并完成一次登录，`login()` 后断言 `is_authenticated`）。
  - 必须与 `session_http_client` 分开建实例，否则未登录用例会带上令牌。
- `pytest_runtest_makereport` 钩子：失败时生成诊断报告到 `ai_debug_reports/`。
  - **pytest 9 兼容**：用 `call.excinfo` 取异常（`report.excinfo` 已移除）；
    `call.excinfo.tb` 取 traceback，`report.longrepr` 在 pytest 9 是 `ExceptionChainRepr`，
    不要直接取 `.tb`。
  - 响应对象常常是用例内的局部变量，不在 `item.funcargs` 里 →
    需要从 traceback 栈帧的局部变量里按 `response/resp/res/r` 名字找。
  - 代码片段提取时 `start` / `end` 要在 try 之前初始化，否则报
    `cannot access local variable 'start'`。

### 4.9 `test_case/conftest.py` — 数据工厂

- `student_factory`：`create(**overrides)` / `update(student_id, **fields)` / `cleanup()`，
  外加 `client`（工厂内部用的已登录客户端）。
- `subject_factory`：`create(**overrides)` / `cleanup()`，同样暴露 `client`。
- 清理放 `yield` 之后 —— 无论用例是否走到结尾、是否断言失败，数据都会被清掉。

### 4.10 `test_case/` 测试文件

| 文件 | 内容 |
|---|---|
| `test_login.py` | YAML 数据驱动：`@pytest.mark.parametrize("case", CASES, ids=lambda c: c.pytest_id)`，一个函数跑完全部用例；断言状态码 + message + `expect_json` 逐字段 JSONPath 断言 |
| `test_login_demo.py` | 传统断言 2 条 + AI 断言 `strict=False` / `strict=True` 各 1 条 |
| `test_demo_fail.py` | 故意失败 2 条（写错状态码期望值、用错请求方法），带 `demo_fail` 标记 |
| `test_student_flow.py` | 业务流程：`@allure.feature` / `@allure.story` / `@allure.title` / `with allure.step(...)` |
| `test_subject_flow.py` | Excel 数据驱动 + 学科业务流程 |

- 异常场景必须逐条覆盖提示词里点名的每一项。
- **断言结论按实测写，不要臆测**。实测契约常见形态：
  - 新增成功 → 201，`message=学生创建成功`；查询 → 200，`message=获取学生详情成功`；
  - 删除成功 → 200，`message=学生已删除`；
  - 必填缺失 → 422，`code=VALIDATION_ERROR`，`message=数据验证失败`，`detail[0].type=missing`；
  - 未带令牌 → 401，`code=UNAUTHORIZED`，`message=请先登录`；
  - 资源不存在 → 200 + `message=学生不存在` + `data=null`（**不是 404**）。
- **占位符替换只能替「值恰好等于占位符」的字段**。
  异常用例常故意写固定长字符串（如「编码超过二十个字符」写死 26 个字符），
  如果按「存在 code 字段就替换」的规则去替，校验场景就没了，
  用例会从「期望 422」变成「实际 201」。
- **「删除成功」必须在清理之前断言**。
  `factory.cleanup()` 是兜底清理，调用后数据已经没了，
  之后再删只会拿到「资源不存在」，永远验证不到删除成功的正常路径。
  正确顺序：用例内先 DELETE 断言「已删除」→ 再查一次断言「不存在」→
  交给 teardown 的 cleanup 兜底。
- **数据驱动的创建类用例必须自带清理**。
  数据驱动的用例不进工厂夹具，工厂的 cleanup 管不到它，
  每次跑都会在库里留一条数据，越积越多。
  做法：用例末尾从响应里取 `data.id`，再调一次 DELETE 清理；
  异常用例服务端已回滚，取不到 id 就跳过。

### 4.11 根目录配置

- `.env`：`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`，并在 `.gitignore` 里排掉。
- `pytest.ini`：`markers` 注册（`smoke` / `crud` / `auth` / `ai` / `demo_fail`）、
  `testpaths = test_case`、`addopts = -v -s`、
  `disable_test_id_escaping_and_forfeit_all_rights_to_community_support = True`（保留中文用例 id）。
- `cli.py`：路径基于 `os.path.dirname(os.path.abspath(__file__))` 计算，
  产物落 `<项目目录>/report/allure-results` 与 `allure-report`，
  末尾 `pytest.main(pytest_args + sys.argv[1:])` 转发用户追加的参数。

---

## 5. 命名规范（生成时统一套用）

- 模块文件名大写下划线：`AI_HttpClient.py`；其余小写下划线。
- 类名大驼峰：`HttpClient` / `ApiCase`。
- 函数名小写下划线；私有工具加 `_` 前缀；pytest 夹具不用 `_` 前缀。
- 测试函数名 `test_<场景>_<对象>`，用例编号 `<模块前缀>-<维度>-<三位序号>`。
- fixture 名：会话级 `session_*` / `auth_*`；工厂级 `*_factory`。

---

## 6. 交付前自检清单

- [ ] 目录树与第 3 节完全一致，文件名一字不差
- [ ] 全部 `【】` 占位符已按用户答复落地，代码里不残留默认值
      （`grep -rn "day10\|localhost:8000\|admin123" <新目录>` 逐条核对，
      只保留用户确认过的取值）
- [ ] `utils/` 下无 `untils/` 拼写错误
- [ ] `ai_prompts.py` 只用标准库，全项目 `urlopen` 只在 `ai_debug_helper.py` 出现一次
- [ ] 源码里没有硬编码的 API Key（只在 `.env` 里，且 `.env` 已被 `.gitignore` 排除）
- [ ] 所有路径由 `Path(__file__).resolve()` 推导，无绝对路径
- [ ] `python -m pytest test_case --collect-only` 能全部收集，无 ImportError
- [ ] 排除演示用例后全绿：`python -m pytest test_case -v -m "not demo_fail"`
- [ ] `test_demo_fail.py` 失败后在 `ai_debug_reports/` 生成了诊断报告
- [ ] 执行完数据无残留：学生数、学科数回到运行前
- [ ] **鉴权用例真的登录成功了**（不是 401）。
      Windows 上系统自带 `USERNAME` 环境变量，
      配置层若直接读 `USERNAME` 会拿到当前登录用户，所有鉴权用例会全灭。
- [ ] 异常用例仍然触发预期的校验错误（不是被占位符替换逻辑改成了正常路径）

---

## 7. 交付说明写法

交付时给出：

1. 目录树（标注每个文件的职责一行）。
2. 生效的关键取值（项目目录名、base_url、接口前缀、账号、核心接口、异常场景）。
3. 三条常用命令：
   ```powershell
   python -m pytest test_case -v -m "not demo_fail"   # 跑全量
   python cli.py                                        # 跑全量 + 生成 Allure 报告
   $env:BASE_URL="http://127.0.0.1:8000"; python -m pytest test_case -v   # 换地址
   ```
4. 若默认端口不通，明确说明「配置层支持 `$env:BASE_URL` 覆盖，不需要改代码」。

---

## 8. 维护本技能

基准副本在 `references/day10/`。day10 线上目录有改动时同步更新：

```powershell
# 排除产物目录，只同步源文件
python -c "import os,shutil; SRC=r'd:\AI_API_AUTO2.0\day10'; DST=r'd:\AI_API_AUTO2.0\.trae\skills\api-test-framework-scaffold\references\day10'; EX={'report','ai_debug_reports','__pycache__','.pytest_cache'}; [ (os.makedirs(os.path.join(DST,os.path.relpath(r,SRC)) if os.path.relpath(r,SRC)!='.' else DST, exist_ok=True), [shutil.copy2(os.path.join(r,f), os.path.join(DST,os.path.relpath(r,SRC),f)) for f in fs]) for r,ds,fs in os.walk(SRC) if not (ds.__setitem__(slice(None),[d for d in ds if d not in EX]))]"
```

同步后必须做的两件事：

1. 把 `references/day10/.env` 改名成 `.env.template` 并把密钥脱敏。
2. 更新本文件里与基准不一致的描述（默认值、目录树、清单）。

