---
name: api-testcase-designer
description: Design executable interface test cases from given API information and output an Excel case list. Use when the user provides API details (URL, method, params, responses, DB tables, business rules) and asks for 接口测试用例, 测试用例设计, or 用例清单. Do not use for writing test automation code.
---

# API Test Case Designer

Turn API information into a complete, executable interface test case set, delivered as an Excel workbook.

## Non-negotiable constraints

1. **Never invent.** Anything not present in the provided API information is written as「需确认：xxx」at that exact position. If design cannot continue without it, state the assumption inline as「（假设：xxx）」.
2. **Every case runs standalone.** No 「正常情况」「异常情况」「合法输入」. The executor must be able to run a case without reading another one.
3. **Every expected result is judgeable.** Concrete status codes, field names, field values, DB table/column/value. 「返回正确结果」is forbidden.
4. **Three assertion blocks in every case** — never merge or skip:
   - 接口返回 — HTTP status code, business code, field names, field types, field values
   - 数据落库 — table name, column, expected value. Required for any write operation
   - 安全与日志 — sensitive data masking, account-enumeration risk, log redaction, parameter validation
5. **Case count 30–60 per interface.** Sort output P0 → P1 → P2 → P3.

## Required coverage — three dimensions

Mark any dimension as 「不适用」with a stated reason rather than silently skipping it.

### 1. FUNC 正常功能
Happy path with full response structure check (every field present, correct type, correct value) · subsequent authenticated endpoints reachable with the issued token · failure branches (wrong password / account not found) · response consistency between failure branches to block account enumeration · side-effect verification after success

### 2. PARAM 入参校验
Required and optional parameters · empty string · explicit `null` · absent key · empty body · wrong JSON type (number, array, object) · length boundaries (min-1, min, max, max+1) · format rules · special characters and injection payloads on **every** string parameter, not just username · extra unknown parameters · parameter pollution (client-supplied identity or role fields) · duplicate JSON keys · malformed JSON · wrong Content-Type

### 3. BIZ 业务规则与状态
State machine transitions and illegal transitions · count and frequency limits (lockout thresholds, rate limits) · validity periods · multi-client concurrency · business constraint combinations

## Case ID format

`{MODULE_PREFIX}-{DIM}-{NNN}` — for example `LOGIN-SEC-001`

| Prefix | Dimension | Covers |
|---|---|---|
| FUNC | 功能 | Happy path, response structure, field completeness, downstream usability |
| PARAM | 入参 | Type, length, format, boundary, special chars, missing, extra, pollution, malformed JSON |
| BIZ | 业务规则 | State machine, illegal transitions, count/frequency limits, validity, concurrency |
| EXCP | 异常 | Timeout, dependency failure, duplicate submit, idempotency, large payloads |

Numbering restarts at 001 within each prefix+dimension pair. An ID is never reused.

## Priority

| Level | Meaning | Execution |
|---|---|---|
| P0 | Core happy path and fatal security issues — horizontal/vertical privilege escalation, injection, token identity mix-up, sensitive data leakage | Every release |
| P1 | Main business rules and important failure branches — lockout, expiry, error handling, enumeration prevention | Per version |
| P2 | General input validation and boundary values | End of version or on demand |

## Case list columns — fixed order

`用例编号 | 所属模块 | 用例标题 | 优先级 | 前置条件 | 请求方式 | 请求参数 | 执行步骤 | 预期结果`

Write 预期结果 as three numbered lines in one cell:

```
1. 接口返回：...
2. 数据落库：...
3. 安全与日志：...
```

## Mandatory self-check before delivering

- [ ] Any case touching password, captcha, ID number, or phone asserts redaction in **both** the response body and logs
- [ ] Any case with a failure message asserts it cannot be used to enumerate accounts (compare wording, body length, and response time across branches)
- [ ] Any write operation has duplicate-submit and concurrent cases
- [ ] Every security case states its exact payload — `' or '1'='1`, `admin'--`, `<script>alert(1)</script>`, `' OR SLEEP(5)--`, `%00`
- [ ] Every write case verifies the database, not only the API response
- [ ] Every case not backed by provided API information is labeled 需确认, not silently assumed

## Output

Workbook with three sheets:

1. **用例清单表** — the 30–60 cases in the fixed column order above
2. **P0P1用例详情卡** — one expanded card per P0/P1 case: ID, module, title, priority, preconditions, method, params, numbered steps, the three expected-result blocks, notes
3. **待确认项清单** — every 需确认 item consolidated, with the case ID it belongs to

Generate the file with `scripts/generate_xlsx.py`, which takes a JSON spec and writes all three sheets with consistent formatting.

## Script usage

```bash
python scripts/generate_xlsx.py <cases.json> -o <output.xlsx>
```

The JSON spec holds a `meta` object and a `cases` array; `references/spec.md` documents every key. Write the JSON by hand from the API information — do not generate cases programmatically, since case content requires design judgment.

## Writing the case content

**用例标题** — verb + object + condition: 「密码错误时登录失败且不返回任何令牌」. Never 「登录异常测试」.

**前置条件** — name the account, its initial state (normal / disabled / locked / fail-count value), and any ordering dependency. Write the concrete initial fail count, because count-threshold cases are otherwise not reproducible.

**请求参数** — write the actual value, including the injection payload or boundary value. 「传一个非法值」is not executable.

**执行步骤** — numbered, one action per step, each step saying what to record. Include the verification SQL for write cases so the executor can check the database without designing it.

**预期结果-接口返回** — assert absence as well as presence: 「响应体中不存在 access_token 字段」. Add timing assertions where a side channel exists, e.g. two failure branches must differ by under 100 ms in mean response time.

**预期结果-数据落库** — if the API information contains no table definitions, write 「不适用（文档未提供数据表信息）」and add the item to 待确认项清单. Do not fabricate table names.

**预期结果-安全与日志** — state what must not leak, what the log must mask, and whether enumeration is possible. When the provided information does not define a rule, phrase it as a question to confirm, not as an assumed defect.