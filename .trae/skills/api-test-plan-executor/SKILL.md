---
name: api-test-plan-executor
description: Execute a Chinese-language interface test plan that is stored as plain-text files (测试计划 → 编排流程 → 测试数据 → 测试用例) and produce a self-contained HTML execution report. Runs every HTTP call and database query directly through the shell, without authoring or running any test script, test framework, or automation code. Use when the user points at a 测试计划 / 编排流程 folder, asks to 执行计划 / 跑一遍用例 / 执行编排, or asks for a 执行报告. Not for designing test cases (use api-testcase-designer) and not for generating an automation framework (use api-test-framework-scaffold).
---

# 接口测试计划执行器

按「测试计划 → 编排流程 → 测试数据 → 测试用例」四层顺序，把纯文本描述的接口测试计划真正跑一遍，
最后产出一份自包含的 HTML 执行报告。

**核心约束：执行全程不写、不跑任何测试代码。** 没有 pytest 文件、没有 `.py` 脚本、没有 requests 封装、
没有断言库。请求是用 Shell 发起的即时命令，数据库是用即时命令查的，断言是逐条对照后人工判定的。
所有辅助文件只允许存在于系统临时目录，执行结束即删除。

---

## 1. 输入结构与解析规则

计划目录形如（`04-测试计划` / `03-编排流程` / `02-测试数据` / `01-测试用例` 四层）：

```
<plan-root>/
├── 04-测试计划/计划N-xxx.txt      ← 入口，指明要执行哪些编排
├── 03-编排流程/编排N-xxx.txt      ← 执行顺序、用例清单、上下文传递规则
├── 02-测试数据/xxx数据.txt        ← 变量值、动态查询规则
└── 01-测试用例/用例N-xxx.txt      ← URL/方法/请求体/断言
```

### 1.1 解析顺序（不可跳步）

1. 读 `04-测试计划/` 下全部计划文件 → 确认本次执行哪些计划
2. 读计划文件里点名的每个 `03-编排流程/编排N-xxx.txt` → 拿到编排名、要跑哪些用例、执行顺序
3. 读编排文件里点名的每个 `02-测试数据/*.txt` → 拿到变量值
4. 读编排文件里点名的每个 `01-测试用例/用例N-xxx.txt` → 拿到接口定义与断言

**严格按引用关系读，不要凭目录顺序瞎扫。** 编排文件是唯一的调度中心，它同时引用了数据文件和用例文件。

### 1.2 变量占位符 `{{变量名}}`

用例与编排文件里用 `{{...}}` 引用测试数据中的值。解析时建立一张变量表：

| 变量名 | 来源 | 示例 |
|---|---|---|
| `{{API_BASE_URL}}` | 账号数据.txt / 各数据文件 | `http://localhost:8000` |
| `{{登录接口路径}}` | 账号数据.txt | `/api/v1/auth/login` |
| `{{正确用户名}}` / `{{正确密码}}` | 账号数据.txt | `admin` / `admin123` |
| `{{成功状态码}}` | 账号数据.txt / 搜索数据.txt | `200` |
| `{{访问令牌变量}}` | 账号数据.txt（变量名，不是值） | `access_token` |
| `{{新姓名}}` / `{{班级ID}}` / `{{目标学生学号}}` | 学生数据.txt | `接口自动化小测` / `1` / `S001` |

**同一个变量名可能在多个数据文件里出现（如 `{{成功状态码}}` 在账号数据.txt 是 200、在搜索数据.txt 是 700）。**
取值规则：优先取**该用例所属编排显式引用的数据文件**；仍无法确定时，取编排链上最后一次声明的值，并在报告中标注该冲突。

### 1.3 动态查询规则（数据文件里的 `动态查询：` 行）

形如：

```
动态查询：学生ID = query_student_info(condition_type=student_no, condition_value=目标学生学号, limit_count=1) 取 student_ids 的第一个
```

拆成三步执行：
1. `condition_type` / `condition_value` → 决定 SQL 的 WHERE 条件与值
2. `limit_count` → 决定 LIMIT
3. 结果取 `student_ids`（或查询结果行）的**第一个**元素，作为目标 ID

等价 SQL（按实际表结构写）：

```sql
SELECT id FROM students WHERE student_no = 'S001' LIMIT 1
```

---

## 2. 执行协议（无代码）

### 2.1 铁律

| 禁止 | 允许 |
|---|---|
| 新建 `.py` / `.ps1` / `.bat` 脚本 | 在 Shell 里敲一次性命令 |
| 写 pytest 用例、requests 封装、断言库 | 直接用 `Invoke-WebRequest` / `curl` 发请求 |
| 改被测服务代码 | 只读不写被测工程 |
| 在计划目录里留任何临时文件 | 临时文件只放系统 TEMP，执行完即删 |
| 臆造断言 | 只跑用例文件里明写的断言 |

**临时脚本例外**：若单条命令过长难以在命令行内完成，允许在 `$env:TEMP` 下写一个一次性 `.py` 并立即执行、
随即删除。绝不允许把文件留在计划目录或工作区内。

### 2.2 HTTP 请求（PowerShell 5.1）

**必做 UTF-8 编码处理。** PowerShell 5.1 的 `Invoke-WebRequest -Body "字符串"` 默认按 ASCII 编码发送，
中文参数会变成 `?`，接口却照样返回 200 —— 断言和落库双重失真且不报错。

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$json = '{"name":"接口自动化小测"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)      # ← 必须转字节
$resp = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/students/1" -Method Put `
        -Body $bytes -Headers @{ Authorization = "Bearer $token" } `
        -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec 15
$ms = New-Object System.IO.MemoryStream
$resp.RawContentStream.CopyTo($ms)
$text = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())   # ← 必须按 UTF-8 解码
$j = $text | ConvertFrom-Json
```

要点：
- 请求体含中文 → 一律 `[System.Text.Encoding]::UTF8.GetBytes()`
- 响应体含中文 → 一律走 `RawContentStream` + `UTF8.GetString()`，不要直接用 `$resp.Content`
- 查询参数含中文 → `[System.Uri]::EscapeDataString($kw)`
- 4xx/5xx 时 `Invoke-WebRequest` 会抛异常，用 `$_.Exception.Response.GetResponseStream()` 取错误体

### 2.3 数据库查询

本机**没有 mysql 客户端**，用 Python + pymysql。工作区 venv 已装好：

```powershell
& 'd:\AI_API_AUTO2.0\venv\Scripts\python.exe' -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3306,user='root',password='123456',database='eduscore',charset='utf8mb4'); cur=c.cursor(); cur.execute('SELECT id,name FROM students WHERE student_no=%s LIMIT 1',('S001',)); print(cur.fetchall())"
```

连接参数从 `day12/.env` 读取（`EDU_DB_HOST/PORT/USER/PASSWORD/NAME/CHARSET`）。

### 2.4 上下文传递

编排文件里的 `上下文传递：` 行说明用例之间怎么传值。典型：

```
上下文传递：用例1 产出的 access_token 写入上下文，用例2 从上下文读取作为 Authorization
```

维护一个贯穿整个计划执行的**上下文变量表**（`access_token` → 具体令牌串）。
编排2 依赖编排1 的产出时，**必须复用编排1 写入的值**，不得重新登录绕过依赖 ——
否则测的就不是编排链路本身。令牌过期（401）时，先记录，再重新获取并在报告中注明。

### 2.5 断言判定

逐条对照用例文件的 `响应断言：` 执行，每条给 PASS / FAIL / BLOCKED，并记录**实际值**。
任何断言的预期值与接口契约不符时（如状态码写成 700），判定为 **FAIL（数据缺陷）**，
并在报告的「数据缺陷」区列出该问题与契约实际值 —— 不要把数据写错说成接口有问题。

可交叉验证的契约来源：

```
GET {API_BASE_URL}/openapi.json
```
能直接拿到该接口声明的成功状态码、参数、请求体 schema、响应字段，比用例文本更权威。

### 2.6 数据落库校验

写操作类用例（POST/PUT/DELETE）必须额外查库确认落库，不能只看接口响应：

```sql
SELECT id, student_no, name, HEX(name) FROM students WHERE id = 1
```
用 `HEX(name)` 判断中文是否真的按 UTF-8 落库，避免存成 `???????` 却看不出来。

---

## 3. HTML 执行报告

### 3.1 产出位置

`<plan-root>/05-执行报告/计划N-执行报告.html`

### 3.2 结构（参考 `references/report-template.html`）

自包含单文件：内联 CSS，不引外部 CDN，不依赖任何脚本即可在浏览器打开。

必须包含：

1. **报告头** — 计划名、执行时间、环境（base_url）、总体结论横幅
2. **统计条** — 用例总数 / 通过 / 失败 / 阻塞，含占比
3. **用例执行明细表** — **本表是核心交付物**，三列固定为：

   | 测试用例 | 执行数据 | 执行结果 |
   |---|---|---|
   | 用例编号、用例名称、优先级、所属编排 | 请求行、方法+URL+关键参数、实际响应体摘要 | PASS/FAIL 徽章 + 逐条断言结果 + 失败原因 |

   「执行数据」列要能让人**独立复现这次调用**：完整 URL、HTTP 方法、请求体原文、响应状态码、响应体关键片段。
   响应体过长时截断并标注 `…(已截断)`。
4. **断言明细** — 每条断言一行：断言描述 / 预期 / 实际 / 判定
5. **上下文传递记录** — 谁产出、谁消费、变量名与值（令牌脱敏为 `eyJ...3KQY`）
6. **数据缺陷与风险** — 如测试数据与接口契约不符、库中残留脏数据等
7. **结论与建议** — 逐条列出可执行的改进项

### 3.3 样式要求

- 浅色为主，`.dark` 不做强制；表格 `border-collapse`，行 hover 有底色变化
- 状态徽章：PASS 绿 / FAIL 红 / BLOCKED 橙 / SKIP 灰，用语义色仅表达状态
- 代码与 URL 用等宽字体，`word-break: break-all`
- 「执行数据」列建议用 `<pre>` 包裹原始报文，保留换行
- 表格 `font-size` ≥ 13px，单元格 `padding` ≥ 8px

---

## 4. 执行流程

1. **读计划** → 确认计划文件、目标编排、执行顺序
2. **环境自检** → 确认 `{API_BASE_URL}/openapi.json` 可达；不可达则直接 BLOCKED 并出报告，不要硬跑
3. **建变量表** → 解析所有被引用的数据文件；冲突项标注
4. **契约预检** → 拉 openapi.json，把用例里的方法/路径/状态码与契约比对，不一致先记为数据缺陷
5. **逐编排逐用例执行** → 按编排声明的顺序；每条请求记录原始报文；每条断言单独判定
6. **动态查询** → 需要 ID 时按 1.3 规则先查库
7. **落库校验** → 写操作后查库
8. **上下文回写** → 产出的变量写回上下文表
9. **出报告** → 按第 3 节生成 HTML
10. **清理** → 删除临时目录里的中间文件

---

## 5. 报告语气与诚实要求

- **只写跑出来的**。没跑的用例标 BLOCKED 并说明原因，不许臆造响应
- **预期值与实际值都写出来**，让人一眼看出差在哪
- 断言失败时区分三种归因：**接口缺陷** / **测试数据缺陷** / **环境问题**，不要混为一谈
- 报告中出现的每个数字都必须来自真实执行输出
- 报告里的 `执行数据` 必须与实际发出的请求逐字对应（URL、请求体原样）

---

## 6. 调用示例

```
执行 day15\hat-api-runner\04-测试计划\计划1-学生管理接口冒烟流程.txt，
按编排顺序跑完所有用例，最后出 HTML 执行报告
```
