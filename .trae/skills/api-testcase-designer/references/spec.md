# JSON Spec

`scripts/generate_xlsx.py` reads this structure and writes three sheets.

## Top level

```json
{
  "meta": { "...": "..." },
  "cases": [ { "...": "..." } ]
}
```

## meta

| Key | Required | Meaning |
|---|---|---|
| `module` | yes | Module name used in 所属模块 column, e.g. `"登录 / 认证"` |
| `api` | yes | Method plus path, e.g. `"POST /api/v1/auth/login"` |
| `title` | no | Workbook title used in header note |

## cases[]

| Key | Required | Maps to column | Notes |
|---|---|---|---|
| `id` | yes | 用例编号 | Format `{PREFIX}-{DIM}-{NNN}` |
| `title` | yes | 用例标题 | Verb + object + condition |
| `priority` | yes | 优先级 | `P0` / `P1` / `P2` / `P3` |
| `precondition` | yes | 前置条件 | Name account, initial state, fail count, dependencies |
| `method` | yes | 请求方式 | Usually equals `meta.api`; override only for multi-endpoint cases |
| `params` | yes | 请求参数 | Concrete values including payloads and boundary values |
| `steps` | yes | 执行步骤 | Array of strings, one action per entry; include verification SQL |
| `expected_return` | yes | 预期结果 line 1 | HTTP status, business code, fields, types, values |
| `expected_db` | yes | 预期结果 line 2 | Table, column, expected value; write 不适用 when no schema given |
| `expected_security` | yes | 预期结果 line 3 | Masking, enumeration, log redaction, validation |
| `note` | no | 备注 | 需确认 items specific to this case |

## pending[] (optional third sheet)

| Key | Required | Meaning |
|---|---|---|
| `case_id` | no | Owning case, or empty for global items |
| `category` | yes | Grouping, e.g. `成功响应` |
| `item` | yes | What needs confirming |
| `impact` | yes | Why it matters or what it blocks |

## Example

```json
{
  "meta": {
    "module": "登录 / 认证",
    "api": "POST /api/v1/auth/login"
  },
  "cases": [
    {
      "id": "LOGIN-FUNC-001",
      "title": "正确账号密码登录成功并返回完整响应结构",
      "priority": "P0",
      "precondition": "1. 账号 admin 已注册且状态正常\n2. 已获取正确密码\n3. 接口服务可达",
      "method": "POST /api/v1/auth/login",
      "params": "Header: Content-Type: application/json\nBody: {\"username\": \"admin\", \"password\": \"admin123\"}",
      "steps": [
        "Postman 新建请求，URL={base_url}/api/v1/auth/login",
        "Header 填 Content-Type: application/json",
        "Body 选择 raw → JSON，填入上述请求体",
        "发送请求，记录 HTTP 状态码与响应体全文",
        "核对响应体顶层字段集合并记录各字段类型",
        "用返回的令牌调用后续鉴权接口（需确认：接口路径），核对返回身份"
      ],
      "expected_return": "HTTP 状态码 = 200；响应体字段集合严格等于 {access_token, expires_in, token_type, user}；access_token 为非空字符串；token_type = \"bearer\"；user.id 为整数",
      "expected_db": "需确认：文档未提供数据表信息；若存在登录日志表，需核对新增 1 条记录且 user_id 与该账号一致",
      "expected_security": "响应体不含 password、password_hash 等字段；不含数据库异常与堆栈；日志中密码字段已脱敏（需确认：脱敏格式）",
      "note": "需确认：令牌有效期"
    }
  ],
  "pending": [
    {
      "case_id": "",
      "category": "成功响应",
      "item": "令牌字段名与结构",
      "impact": "未提供，无法确定响应字段断言"
    }
  ]
}
```

## Formatting applied by the script

- Font Arial 10pt throughout
- Header row: dark blue fill `1F3864`, white bold text
- Data rows: zebra striping `FFFFFF` / `F7F9FC`
- P0 rows: light blue fill `EAF2FF` with red bold priority text
- Thin borders in `D9DEE7`
- Wrap text on all long-text columns; centered alignment for ID, module, priority, method
- Row height 150 for case rows, frozen header, auto filter on the case list sheet
- Case list columns: A 18, B 11, C 30, D 8, E 34, F 20, G 40, H 60, I 76