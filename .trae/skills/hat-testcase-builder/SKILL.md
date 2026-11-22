---
name: hat-testcase-builder
description: 把自然语言的测试场景转换成 HAT 框架可直接执行的 YAML 用例，同时支持接口用例（ApiCase）和 Web UI 用例（WebCase）。触发场景：用户给出接口信息（URL、方法、参数、响应示例、业务规则）或页面操作描述，或用中文描述测试场景，要求生成 HAT 用例、写 yaml 用例、补充测试场景、做数据驱动用例。不用于设计 Excel 用例清单（用 api-testcase-designer），也不用于生成 pytest 框架代码（用 api-test-framework-scaffold）。
enabled: true
---

重点：请使用中文沟通！！

# hat-testcase-builder — HAT 用例构建器

把用户给出的接口信息或中文测试场景，转换成符合 HAT 框架规范的 YAML 用例文件，
落盘到指定用例目录后可以直接被 HAT 执行，**不需要写任何 Python 测试代码**。

## 不可违反的约束

1. **不许编造。** 接口信息里没有的字段、路径、期望值，在该位置写「需确认：xxx」，
   并向用户追问；不得虚构响应字段或业务规则。
2. **只生成 YAML 用例文件和 context.yaml，不改框架代码。**
   HAT 的关键字已覆盖请求、提取、断言、查库、AI 断言，优先复用；
   确有需要的新动作，提示用户走 `key_dir` 自定义关键字机制，不要顺手改 `HAT/` 下的源码。
3. **生成后必须自检**：执行 `pytest --collect-only` 确认用例能被正确收集（见第 5 节）。

## 1. 先确认用例落盘位置

- 默认写到用户指定的用例目录；未指定时用 `examples/api_cases_yaml/` 风格新建目录，
  例如 `<项目根>/cases/<模块名>/`。
- 目录里可以放一个 `context.yaml` 承载公共变量（base_url、账号、复用开关）。
  若用户给的场景跨环境，base_url 一律放 `context.yaml`，用例里只写 `{{url}}`。
- 用例文件命名：**数字前缀 + 下划线 + 描述**，如 `1_login.yaml`、`2_create_user.yaml`。
  HAT 按数字前缀升序加载，前缀即执行顺序。
- 不确定用户要覆盖旧文件还是新增时，先问。

## 2. HAT YAML 用例格式（必须严格遵循）

```yaml
basic_configuration:
  case_type: "ApiCase"        # ApiCase / WebCase，接口场景用 ApiCase，页面场景用 WebCase（见第 7 节）
  case_title: "login"         # 用例名，同时用于 pytest ID 和 Allure 标题
  module: "authentication"    # 所属模块，对应 Allure feature
  function: "login"           # 业务功能，对应 Allure story

setup_script:                 # 可选，前置脚本列表，元素为 Python 语句字符串
  - ""

teardown_script:              # 可选，后置脚本列表
  - ""

case_steps:                   # 必填，按顺序执行的步骤列表
  - 步骤名:                    # 每步只有一个键，键名即 Allure 步骤名
      request_method: "关键字名"
      参数名: "参数值"          # 其余键全部作为关键字参数传入
```

规则细节（容易踩坑的地方）：

- `request_method` 的值必须是下表中的关键字名，写错会在执行期 AttributeError。
- 没用的请求参数字段照抄示例写成空字符串 `""`，不要省略键（与示例用例保持一致）。
- `request_payload` 有值时 `content_type` 必须显式写 `"json"` 或 `"data"`。
- 变量一律用 Jinja2 语法 `{{变量名}}`；变量来源只有两个：
  `context.yaml` 的键，或前面步骤 `get_json_data` / `fetch_database_data` 存下的 `variable_name`。
  **引用不存在的变量是最高频错误**，生成后逐个核对变量名。
- 跨步骤传递数据（如登录拿 token）固定三步走：
  请求步骤 → `get_json_data` 提取存变量 → 后续步骤 `{{token}}` 引用。

## 3. 可用关键字速查

请求类：

| 关键字 | 必填参数 | 说明 |
|---|---|---|
| `post_request` | `request_url`、`content_type` | 另有 `request_parameters`、`request_headers`、`request_payload`、`file_path` |
| `get_request` | `request_url` | 另有 `request_parameters`、`request_headers`、`request_payload` |
| `send_request` | `method`、`url` | 通用请求，参数直接透传 requests |

提取与查库：

| 关键字 | 参数 | 说明 |
|---|---|---|
| `get_json_data` | `expression`（JSONPath）、`variable_name`、`index`（默认 0） | 从最近一次响应提取并存入上下文 |
| `fetch_database_data` | `database`（context.yaml 中 `_database` 的别名）、`sql`、`variable_name` | 查库结果存入上下文，变量自动带 `_行号` 后缀 |

断言类：

| 关键字 | 参数 | 说明 |
|---|---|---|
| `assert_text_equal` / `assert_text_contain` / `assert_text_not_contain` | `expected_value`、`actual_value` | 文本断言 |
| `assert_number_equal` / `assert_number_not_equal` / `assert_number_gt` / `assert_number_ge` / `assert_number_lt` / `assert_number_le` | `expected_value`、`actual_value` | 数值断言，自动转 float |
| `ai_assert` | `rule`（必填，中文规则）、`strict`（默认 true）、`context`、`actual_value` | 自然语言断言，不传 `actual_value` 时断言最近一次响应；未配置 LLM_API_KEY 时降级为本地规则 |

断言选型原则：

- **能用确定性断言就不用 AI 断言**。状态码、字段值相等、包含关系，用 `assert_*`。
- 以下情况用 `ai_assert`：规则本身是模糊语义（"列表按时间倒序"、"错误信息是友好提示"）、
  字段结构复杂难以 JSONPath 表达、探索阶段想快速验证。
- `ai_assert` 的 `strict: "false"` 适合观察期——只记录结论，不让用例失败。

## 4. 数据驱动（ddt）

同一场景多组数据时，不要复制多份用例，用 `ddt` 从模板展开：

```yaml
ddt:
  - scenario_title: "incorrect_username"
    username: "not_exist@example.com"
    password: "Test123456@"
    expected_value: "Unauthorized"
```

- 每条 ddt 数据并入该用例的本地上下文，`{{username}}` 等直接引用。
- 展开后用例名为 `case_title-scenario_title`，`scenario_title` 必填且要有辨识度。
- 正常场景和异常场景混在一个 ddt 里没问题，但期望值的表达方式要统一
  （例如统一断言错误码字段，而不是有的断言状态码有的断言文案）。

## 5. 生成后自检（必做）

```bash
python -m pytest --collect-only -q HAT/core/test_runner.py \
  --cases_type=yaml --cases_path=<用例目录>
```

- 收集数量应等于「普通用例数 + 各 ddt 场景数」；对不上说明有文件解析失败。
- 用户已配置可用被测环境时，征求同意后可以直接跑一遍；
  失败用例框架会自动生成 AI 诊断报告到 `ai_debug_reports/`，把它一并展示给用户。

## 6. 交付时的汇报格式

向用户说明：

1. 生成了哪些文件、放在哪个目录；
2. 每条用例覆盖了什么场景，ddt 展开了几条；
3. 哪些地方写了「需确认」，等用户补充什么信息；
4. 自检结果（收集到几条用例）；
5. 如何执行：`python -m pytest -v -s HAT/core/test_runner.py --cases_type=yaml --cases_path=<用例目录>`。

## 参考样例

完整可跑的示例在 `examples/api_cases_yaml/`：
`1_login.yaml`（请求 + 提取 + 断言的标准三步）、`0_login_ddt.yaml`（ddt 用法）。
生成前建议先读一眼，保持风格一致。

## 7. Web 用例（case_type: "WebCase"）

Web 用例与 API 用例共用同一套骨架，差异只在步骤关键字和元素配置：

- 元素定位集中在用例目录 `context.yaml` 的 `_all_web_elements`，按页面分组，
  用例步骤里用 `element_position` + `element` 引用；
- 定位写法推荐方言字符串：`placeholder=手机号码`、`role=button[name='登录']`、
  `text=评论`、`xpath=//input[@type='email']`、CSS 直接写选择器；
  旧版 `{"locating_method": "By.XPATH", "expression": "..."}` 字典仍兼容；
- 浏览器行为由 `context.yaml` 的 `_browser_config` 控制
  （`browser_name` / `headless` / `viewport` / `args`）；
- 常用步骤：`open_url` → `input_text` / `click_element` → `get_element_data` 存变量 → `assert_text_*`；
- 页面级模糊断言用 `ai_assert_screenshot`（截图喂视觉模型，参数同 `ai_assert`）：

```yaml
- ai_check:
    request_method: "ai_assert_screenshot"
    rule: "页面右上角显示用户名"
    strict: "true"
```

完整示例见 `examples/web_cases_yaml/`。
