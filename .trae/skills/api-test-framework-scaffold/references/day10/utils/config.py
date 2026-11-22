# -*- coding: utf-8 -*-
"""
day10 / utils / config.py

共享配置与业务常量。

相比 day9 的改进：
    day9 的 BASE_URL 是写死的常量，换环境要改代码；
    day10 改成「多环境配置 + 环境变量覆盖」，
    代码里不出现任何地址，切换环境只改 .env 或环境变量。

配置优先级（从高到低）：
    1. 环境变量 BASE_URL / API_USERNAME / API_PASSWORD
    2. .env 文件里的同名键
    3. 本文件 ENVIRONMENTS 里定义的对应环境默认值

注意：账号配置项用 API_USERNAME / API_PASSWORD 而不是 USERNAME / PASSWORD。
    Windows 系统自带 USERNAME 环境变量（值是当前登录用户，比如 DELL），
    直接读 USERNAME 会把系统用户当成测试账号，导致登录永远返回 401。
    加 API_ 前缀可以避开所有系统级同名变量。

用法：
    # 用例里直接引用
    from day10.utils.config import BASE_URL, LOGIN_PATH, STUDENTS_PATH

    # 切换环境（Windows PowerShell）
    $env:BASE_URL="http://localhost:8000"; python -m pytest test_case -v
    $env:API_USERNAME="admin"; $env:API_PASSWORD="admin123"; python -m pytest test_case -v
"""

# 标准库：环境变量读取
import os

# 标准库：路径处理
from pathlib import Path

# 标准库：时间戳生成唯一学号
import time

# ============================================================================
# 1. 路径引导
#    本文件在 day10/utils/ 下，上溯一级是 day10，上溯两级是项目根
# ============================================================================

# day10 目录
DAY10_DIR = Path(__file__).resolve().parent.parent

# 项目根目录
PROJECT_ROOT = DAY10_DIR.parent


# ============================================================================
# 2. .env 读取
#    用 python-dotenv；没装时退化为手工解析，保证不因可选依赖而导入失败
# ============================================================================

def load_env_file(env_file=None):
    """读取 .env 文件，返回键值字典。

    :param env_file: .env 文件路径，None 表示在 day10 目录下查找
    :return: 键值字典
    """
    # 确定 .env 的位置。优先 day10/.env，其次当前工作目录
    candidates = []
    if env_file:
        candidates.append(Path(env_file))
    else:
        candidates.append(DAY10_DIR / ".env")
        candidates.append(Path.cwd() / ".env")

    values = {}
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    # 跳过空行与注释行
                    if not line or line.startswith("#"):
                        continue
                    # 只处理 KEY=VALUE 形式
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    # 去掉可能存在的引号
                    values[key.strip()] = value.strip().strip('"').strip("'")
            # 找到第一个存在的 .env 就用它
            break
        except OSError:
            continue

    return values


# 读取 .env 内容。模块导入时执行一次
ENV_VALUES = load_env_file()


# 系统级环境变量黑名单。
# Windows / Linux 都自带同名变量，取值与测试配置毫无关系，
# 一旦被 get_config 读到就会静默污染配置（典型：USERNAME=DELL 被当成登录账号）。
# 这些键即便出现在环境变量里也一律忽略
SYSTEM_ENV_BLOCKLIST = {
    "USERNAME",
    "USER",
    "LOGNAME",
    "PASSWORD",
    "HOME",
    "PATH",
    "HOSTNAME",
    "COMPUTERNAME",
    "TEMP",
    "TMP",
}


def get_config(key, default=""):
    """按「环境变量 > .env > 默认值」的顺序取配置项。

    环境变量读取会跳过 SYSTEM_ENV_BLOCKLIST 里的系统变量，
    避免系统用户名之类的值被误当成项目配置。

    :param key: 配置项名称
    :param default: 都没取到时的默认值
    :return: 配置值字符串
    """
    # 环境变量优先级最高。系统级同名变量一律跳过
    if key.upper() not in SYSTEM_ENV_BLOCKLIST:
        value = os.environ.get(key)
        if value:
            return value
    # 其次读 .env
    value = ENV_VALUES.get(key)
    if value:
        return value
    # 最后用默认值
    return default


# ============================================================================
# 3. 多环境配置
#    每个环境一套参数，通过 ENV 环境变量选择。
#    未指定 ENV 时默认 dev。
# ============================================================================

# 当前环境名。执行时用 $env:ENV="test" 切换
ENV_NAME = get_config("ENV", "dev")

# 各环境的默认参数。
# 键名与 .env 里的配置项一一对应，缺失时用这里的值兜底。
#
# 地址说明：
#     被测服务（EduScore AI 学生成绩系统）统一监听 8000，
#     各环境默认值都指向 http://localhost:8000。
#     无论哪个环境，都可以用 $env:BASE_URL 临时覆盖，不需要改代码
ENVIRONMENTS = {
    "dev": {
        "BASE_URL": "http://localhost:8000",
        "API_PREFIX": "/api/v1",
        "TIMEOUT": "10",
    },
    "test": {
        "BASE_URL": "http://localhost:8000",
        "API_PREFIX": "/api/v1",
        "TIMEOUT": "15",
    },
    "pre": {
        "BASE_URL": "http://localhost:8000",
        "API_PREFIX": "/api/v1",
        "TIMEOUT": "20",
    },
    "prod": {
        "BASE_URL": "http://localhost:8000",
        "API_PREFIX": "/api/v1",
        "TIMEOUT": "30",
    },
}

# 当前环境的默认参数。未识别的环境名退回 dev
CURRENT_ENV = ENVIRONMENTS.get(ENV_NAME, ENVIRONMENTS["dev"])


# ============================================================================
# 4. 被测服务
# ============================================================================

# 服务基础地址。地址只在这里出现一次，别处一律引用本常量
BASE_URL = get_config("BASE_URL", CURRENT_ENV["BASE_URL"]).rstrip("/")

# 接口统一前缀。所有接口路径都拼在它后面
API_PREFIX = get_config("API_PREFIX", CURRENT_ENV["API_PREFIX"]).rstrip("/")

# 统一超时时间，单位秒
TIMEOUT = int(get_config("TIMEOUT", CURRENT_ENV["TIMEOUT"]))

# 各接口路径。前缀 + 具体路径
HEALTH_PATH = API_PREFIX + "/health"
LOGIN_PATH = API_PREFIX + "/auth/login"
CURRENT_USER_PATH = API_PREFIX + "/auth/me"
USER_AVATAR_PATH = API_PREFIX + "/auth/avatar"
LOGOUT_PATH = API_PREFIX + "/auth/logout"

CLASSES_PATH = API_PREFIX + "/classes"
EXAMS_PATH = API_PREFIX + "/exams"

SUBJECTS_PATH = API_PREFIX + "/subjects/"
SUBJECT_DETAIL_PATH = API_PREFIX + "/subjects/{subject_id}"

STUDENTS_PATH = API_PREFIX + "/students/"
STUDENT_DETAIL_PATH = API_PREFIX + "/students/{student_id}"
STUDENT_AVATAR_PATH = API_PREFIX + "/students/{student_id}/avatar"
STUDENT_TEMPLATE_PATH = API_PREFIX + "/students/import/template"
STUDENT_IMPORT_PATH = API_PREFIX + "/students/import"
STUDENT_EXPORT_PATH = API_PREFIX + "/students/export"

SCORES_PATH = API_PREFIX + "/scores/"
SCORE_DETAIL_PATH = API_PREFIX + "/scores/{score_id}"
SCORE_TEMPLATE_PATH = API_PREFIX + "/scores/import/template"
SCORE_IMPORT_PATH = API_PREFIX + "/scores/import"
SCORE_EXPORT_PATH = API_PREFIX + "/scores/export"

STATS_OVERVIEW_PATH = API_PREFIX + "/stats/overview"
STATS_CLASS_PATH = API_PREFIX + "/stats/class/{class_id}"

ANALYSIS_STUDENT_PATH = API_PREFIX + "/analysis/student/{student_id}"
ANALYSIS_CLASS_PATH = API_PREFIX + "/analysis/class"


# ============================================================================
# 5. 测试账号
# ============================================================================

# 测试账号。admin 具备管理员权限，学生管理的写操作要求管理员
#
# 配置键用 API_ 前缀而不是裸 USERNAME / PASSWORD：
#     Windows 系统自带 USERNAME 环境变量（值为当前登录用户，如 DELL），
#     get_config() 会优先读它，导致拿系统用户名去登录，永远返回 401。
#     加前缀后与所有系统级变量都不会撞名
USERNAME = get_config("API_USERNAME", "admin")
PASSWORD = get_config("API_PASSWORD", "admin123")


# ============================================================================
# 6. 业务常量
# ============================================================================

# 班级 ID。测试环境固定使用高三1班
CLASS_ID = 1

# 班级代码。导入 CSV 时按班级代码关联班级，与 CLASS_ID 指向同一个班
CLASS_CODE = "G3-C1"

# 导入、导出 CSV 的表头，与服务端模板保持一致
CSV_HEADER = "学号,姓名,班级代码,性别,状态"

# 成绩导入、导出 CSV 的表头，与服务端模板保持一致
SCORE_CSV_HEADER = "学号,学科代码,考试名称,分数,备注"

# 性别与学籍状态的合法取值
GENDER_MALE = "男"
GENDER_FEMALE = "女"
STATUS_ENROLLED = "在读"
STATUS_SUSPENDED = "休学"


# ============================================================================
# 7. 用例数据路径
# ============================================================================

# YAML 用例数据目录
YAML_DATA_DIR = DAY10_DIR / "data" / "yaml_data"

# Excel 用例数据目录
EXCEL_DATA_DIR = DAY10_DIR / "data" / "excel_data"

# AI 排错报告输出目录
AI_DEBUG_REPORT_DIR = DAY10_DIR / "ai_debug_reports"


# ============================================================================
# 8. 测试数据生成
# ============================================================================

# 学号计数器。同一条用例内多次取号时保证不重复
_student_no_counter = 0

# 学科代码计数器。同一条用例内多次取号时保证不重复
_subject_code_counter = 0


def generate_student_no(prefix: str = "ST") -> str:
    """生成唯一学号。

    由「前缀 + 毫秒时间戳 + 递增序号」三部分组成：
        前缀用于在数据库中一眼看出数据是哪条用例造的；
        毫秒时间戳保证跨用例不冲突；
        递增序号保证同一毫秒内多次调用也不重复。

    :param prefix: 学号前缀
    :return: 唯一学号
    """
    # 使用 global 声明对模块级计数器的读写
    global _student_no_counter
    # 计数器自增
    _student_no_counter += 1
    # 拼装学号
    return "{}{}{:02d}".format(
        prefix, str(int(time.time() * 1000))[-10:], _student_no_counter
    )


def generate_subject_no(prefix: str = "SB") -> str:
    """生成唯一学科代码。

    组成与 generate_student_no 一致：前缀 + 毫秒时间戳 + 递增序号。
    学科代码长度上限为 20，前缀加 10 位时间戳加 2 位序号刚好在范围内。

    :param prefix: 学科代码前缀
    :return: 唯一学科代码
    """
    # 使用 global 声明对模块级计数器的读写
    global _subject_code_counter
    # 计数器自增
    _subject_code_counter += 1
    # 拼装学科代码
    return "{}{}{:02d}".format(
        prefix, str(int(time.time() * 1000))[-10:], _subject_code_counter
    )
