# -*- coding: utf-8 -*-
import json
import requests
import copy
import yaml
import os
import hashlib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ==============================================================================
# 配置区域 (Configuration)
# ==============================================================================

# 上游规则源地址
UPSTREAM_URL = "https://rules2.clearurls.xyz/data.minify.json"
# 上游规则的 Hash 校验文件地址
UPSTREAM_HASH_URL = "https://rules2.clearurls.xyz/rules.minify.hash"

# 本地文件路径配置
OUTPUT_DIR = "rules"  # 输出目录
UPSTREAM_FILE = os.path.join(OUTPUT_DIR, "upstream_rules.json")  # 上游规则备份 (Pretty)
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR, "merged_rules.json"
)  # 合并后的规则 (Pretty, 人类可读)
MINIFIED_FILE = os.path.join(
    OUTPUT_DIR, "rules.min.json"
)  # 最终产物 (Minified, 插件使用)
MINIFIED_HASH_FILE = os.path.join(OUTPUT_DIR, "rules.min.hash")  # 最终产物的 Hash
BADGE_FILE = os.path.join(OUTPUT_DIR, "badge.json")  # 日期徽章文件
LOG_FILE = os.path.join(OUTPUT_DIR, "merge_log.txt")  # 构建日志
CUSTOM_FILE = "custom_rules.yaml"  # 自定义规则配置文件

# 定义时区：北京时间 (UTC+8)
CN_TZ = timezone(timedelta(hours=8))

# 特殊标记：用于清空某个数组字段
KEYWORD_DELETE_ALL = "DELETE_ENTIRE_ARRAY"

# 默认的 Provider 结构模板
DEFAULT_PROVIDER = {
    "urlPattern": "",
    "completeProvider": True,
    "rules": [],
    "referralMarketing": [],
    "rawRules": [],
    "exceptions": [],
    "redirections": [],
    "forceRedirection": False,
}

# 字段定义
RULE_FIELDS = ["rules", "referralMarketing", "rawRules", "redirections"]
ARRAY_FIELDS = RULE_FIELDS + ["exceptions"]

# ==============================================================================
# 工具类与辅助函数 (Utils)
# ==============================================================================


class MergeLogger:
    """
    日志记录器：
    1. 同时输出到控制台和内存列表。
    2. 收集警告信息以便在日志末尾汇总。
    3. 支持北京时间的时间戳。
    """

    def __init__(self):
        self.lines = []
        self.warnings = []

    def log(self, message):
        """记录普通信息"""
        print(message)
        self.lines.append(message)

    def warn(self, message):
        """记录警告信息 (控制台显示黄色)"""
        print(f"\033[93m{message}\033[0m")
        self.warnings.append(message)
        self.lines.append(message)

    def header(self, upstream_ts, custom_ts):
        """生成日志头部信息"""
        now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
        self.lines.insert(0, "=" * 40)
        self.lines.insert(1, "         ClearURLs Merge Log")
        self.lines.insert(2, "=" * 40)
        self.lines.insert(3, f"Execution Time   : {now} (CST)")
        self.lines.insert(4, f"Upstream Modified: {upstream_ts}")
        self.lines.insert(5, f"Custom Modified  : {custom_ts}")
        self.lines.insert(6, "-" * 40)
        self.lines.insert(7, "")

    def save(self):
        """将日志写入文件"""
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))
            if self.warnings:
                f.write("\n\n" + "=" * 40 + "\n")
                f.write(f"WARNING SUMMARY ({len(self.warnings)})\n")
                f.write("=" * 40 + "\n")
                f.write("\n".join(self.warnings))


def ensure_dir(directory):
    """确保目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)


def normalize_to_list(value):
    """
    核心解析函数：递归处理 YAML 输入。
    支持混合使用列表和字符串块，并处理引号转义。

    输入示例:
      > "a\\b", 'c\b'
    输出:
      ['a\b', 'c\b']
    """
    final_items = []

    # 情况 A: 字符串 (执行切分和引号清洗)
    if isinstance(value, str):
        # 1. 替换逗号为空格并切分 (支持 comma-separated)
        raw_items = value.replace(",", " ").split()

        for item in raw_items:
            # 2. 根据引号类型处理
            if item.startswith("'") and item.endswith("'"):
                # 单引号：Raw模式，内容保留原样 (例如正则: '^https?://')
                final_items.append(item[1:-1])
            elif item.startswith('"') and item.endswith('"'):
                # 双引号：Unescape模式，还原 JSON 风格的反斜杠 (例如: "a\\b" -> a\b)
                # 解决从 JSON 文件直接复制正则时的双重转义问题
                content = item[1:-1]
                final_items.append(content.replace("\\\\", "\\").replace('\\"', '"'))
            else:
                # 无引号：保留原样
                final_items.append(item)
        return final_items

    # 情况 B: 列表 (递归处理每一项)
    if isinstance(value, list):
        for sub_item in value:
            final_items.extend(normalize_to_list(sub_item))
        return final_items

    return []


def calculate_sha256(content_bytes):
    """计算二进制内容的 SHA256 哈希值"""
    return hashlib.sha256(content_bytes).hexdigest()


def format_http_date(date_str):
    """将 HTTP 头中的 GMT 时间转换为北京时间字符串"""
    if not date_str:
        return "Unknown"
    try:
        dt = parsedate_to_datetime(date_str)
        dt_cn = dt.astimezone(CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


def get_file_mtime(filepath):
    """获取文件最后修改时间 (北京时间)"""
    if os.path.exists(filepath):
        ts = os.path.getmtime(filepath)
        dt_cn = datetime.fromtimestamp(ts, CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    return "N/A (File not found)"


# ==============================================================================
# 核心逻辑函数 (Core Logic)
# ==============================================================================


def fetch_upstream(logger):
    """
    获取上游规则：
    1. 下载 JSON 和 Hash。
    2. 校验 SHA256，不匹配则终止。
    3. 保存一份 Pretty 格式的备份。
    """
    logger.log(f"[-] Fetching upstream from {UPSTREAM_URL}...")
    try:
        # 下载 JSON
        r = requests.get(UPSTREAM_URL)
        r.raise_for_status()
        json_bytes = r.content
        data = r.json()

        # 获取时间戳
        raw_date = r.headers.get("Last-Modified")
        formatted_date = format_http_date(raw_date)

        # 下载 Hash
        logger.log(f"[-] Fetching upstream hash from {UPSTREAM_HASH_URL}...")
        r_hash = requests.get(UPSTREAM_HASH_URL)
        r_hash.raise_for_status()
        upstream_hash = r_hash.text.strip()

        # 校验
        local_hash = calculate_sha256(json_bytes)
        if local_hash != upstream_hash:
            raise Exception(
                f"Hash mismatch! Upstream: {upstream_hash}, Downloaded: {local_hash}"
            )

        logger.log("    [Check] Upstream hash verified successfully.")

        # 保存备份
        logger.log(f"[-] Saving upstream backup to {UPSTREAM_FILE}...")
        with open(UPSTREAM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        return data, formatted_date
    except Exception as e:
        logger.log(f"[!] Error fetching/verifying upstream: {e}")
        exit(1)


def load_custom(logger):
    """加载本地 YAML 自定义规则"""
    logger.log(f"[-] Loading custom rules from {CUSTOM_FILE}...")
    custom_ts = get_file_mtime(CUSTOM_FILE)
    if not os.path.exists(CUSTOM_FILE):
        logger.warn("[!] No custom rules file found.")
        return {}, custom_ts
    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}), custom_ts


def upsert_provider(providers, name, patch_data, section_name, logger):
    """
    处理单个 Provider 的合并逻辑 (Add/Modify 均复用此函数)
    """
    if not patch_data:
        return

    exists = name in providers
    action_type = ""

    # 1. 确定操作类型并记录日志
    if section_name == "add-providers":
        if exists:
            logger.warn(f"    [WARN] Duplicate Add: '{name}' exists. Merging changes.")
            action_type = "Merge (Add->Mod)"
        else:
            action_type = "Create"
    elif section_name == "modify-providers":
        if not exists:
            logger.warn(f"    [WARN] Missing Modify: '{name}' missing. Creating new.")
            action_type = "Create (Mod->Add)"
            providers[name] = copy.deepcopy(DEFAULT_PROVIDER)
        else:
            action_type = "Modify"

    # 确保 Provider 存在
    if name not in providers:
        providers[name] = copy.deepcopy(DEFAULT_PROVIDER)

    # 只有非 WARN 状态才记录常规操作日志
    if "WARN" not in action_type:
        logger.log(f"    [{action_type:<6}] {name}")

    target = providers[name]

    # 2. 遍历字段应用修改
    for field, value in patch_data.items():
        value_list = []
        is_array = False
        target_field_name = field

        # 判断是否为数组操作 (rst-, del-, 或标准字段)
        if field.startswith("rst-"):
            target_field_name = field[4:]
            if target_field_name in ARRAY_FIELDS:
                value_list = normalize_to_list(value)
                is_array = True
        elif field.startswith("del-"):
            target_field_name = field[4:]
            if target_field_name in ARRAY_FIELDS:
                value_list = normalize_to_list(value)
                is_array = True
        elif field in ARRAY_FIELDS:
            value_list = normalize_to_list(value)
            is_array = True

        # --- 执行具体逻辑 ---

        # 模式 A: 覆盖 (rst-)
        if field.startswith("rst-"):
            if is_array:
                # 数组覆盖：去重并排序
                target[target_field_name] = sorted(list(set(value_list)))
            else:
                # 标量覆盖 (如 rst-urlPattern)
                target[target_field_name] = value

        # 模式 B: 删除 (del-)
        elif field.startswith("del-"):
            if is_array:
                original_list = target.get(target_field_name, [])
                # 检查全删标记
                if len(value_list) == 1 and value_list[0] == KEYWORD_DELETE_ALL:
                    target[target_field_name] = []
                else:
                    # 检查是否存在 (日志用途)
                    not_found_items = [x for x in value_list if x not in original_list]
                    if not_found_items:
                        logger.warn(
                            f"        [WARN] '{name}': Cannot delete non-existent {target_field_name}: {not_found_items}"
                        )
                    # 执行过滤
                    target[target_field_name] = [
                        x for x in original_list if x not in value_list
                    ]

        # 模式 C: 追加 (标准数组)
        elif is_array:
            original_list = target.get(field, [])
            # 检查重复 (日志用途)
            duplicates = [x for x in value_list if x in original_list]
            if duplicates:
                logger.log(
                    f"        [Info] '{name}' ({field}): Skipped duplicates {duplicates}"
                )

            # 合并去重
            new_set = set(original_list)
            new_set.update(value_list)
            target[field] = sorted(list(new_set))

        # 模式 D: 标量覆盖 (标准字段)
        else:
            target[field] = value

    # 3. 自动计算 completeProvider
    # 逻辑：只要有任意过滤规则，就不是 completeProvider (False)；否则为 True
    if "completeProvider" not in patch_data:
        has_rules = any(len(target.get(f, [])) > 0 for f in RULE_FIELDS)
        target["completeProvider"] = not has_rules


def process_rules(upstream_data, custom_data, logger):
    """主处理流程"""
    logger.log("[-] Processing rules...")
    providers = upstream_data.get("providers", {})

    # 1. 处理删除列表 (Del)
    del_list = normalize_to_list(custom_data.get("del-providers", []))
    for name in del_list:
        if name in providers:
            logger.log(f"    [Delete] {name}")
            del providers[name]
        else:
            logger.warn(
                f"    [WARN] Delete failed: Provider '{name}' not found in upstream."
            )

    # 2. 处理新增列表 (Add)
    add_dict = custom_data.get("add-providers", {}) or {}
    for name, patch in add_dict.items():
        upsert_provider(providers, name, patch, "add-providers", logger)

    # 3. 处理修改列表 (Modify)
    mod_dict = custom_data.get("modify-providers", {}) or {}
    for name, patch in mod_dict.items():
        upsert_provider(providers, name, patch, "modify-providers", logger)

    return {"providers": providers}


def minify_data(data):
    """
    生成 Minified 版本：
    1. 剔除默认值 (forceRedirection: False)。
    2. 剔除空数组。
    3. 特殊逻辑：completeProvider 仅当 True 时保留 (插件默认视为 False?)
    """
    minified_providers = {}

    for name, provider in data.get("providers", {}).items():
        mini = {}
        # 必填项
        if "urlPattern" in provider:
            mini["urlPattern"] = provider["urlPattern"]

        # 仅保留 True
        if provider.get("completeProvider") is True:
            mini["completeProvider"] = True

        # 仅保留 True
        if provider.get("forceRedirection") is True:
            mini["forceRedirection"] = True

        # 仅保留非空数组
        for key in ARRAY_FIELDS:
            val = provider.get(key)
            if val and len(val) > 0:
                mini[key] = val

        minified_providers[name] = mini

    return {"providers": minified_providers}


def generate_badge(logger):
    """生成 Shields.io Endpoint 专用的 JSON"""
    # 获取当前北京时间 YYYY-MM-DD
    now_date = datetime.now(CN_TZ).strftime("%Y-%m-%d")

    badge_data = {
        "schemaVersion": 1,
        "label": "Rules Updated",  # 徽章左边的文字
        "message": now_date,  # 徽章右边的文字 (日期)
        "color": "brightgreen",  # 颜色
        "cacheSeconds": 3600,  # 缓存时间
    }

    logger.log(f"[-] Generating badge json to {BADGE_FILE}...")
    with open(BADGE_FILE, "w", encoding="utf-8") as f:
        json.dump(badge_data, f, indent=None, ensure_ascii=False)


def save_output(data, logger):
    """保存所有输出文件"""
    # 1. 保存 merged_rules.json (Pretty)
    logger.log(f"[-] Saving merged rules to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    # 2. 生成并保存 rules.min.json (Minified)
    logger.log("[-] Generating minified rules...")
    minified_data = minify_data(data)

    logger.log(f"[-] Saving minified rules to {MINIFIED_FILE}...")
    with open(MINIFIED_FILE, "w", encoding="utf-8") as f:
        # separators移除所有空格
        json.dump(
            minified_data, f, indent=None, separators=(",", ":"), ensure_ascii=False
        )

    # 3. 计算并保存 rules.min.hash (SHA256)
    logger.log(f"[-] Calculating hash for {MINIFIED_FILE}...")
    with open(MINIFIED_FILE, "rb") as f:
        content_bytes = f.read()
        file_hash = calculate_sha256(content_bytes)

    logger.log(f"[-] Saving hash ({file_hash}) to {MINIFIED_HASH_FILE}...")
    with open(MINIFIED_HASH_FILE, "w", encoding="utf-8") as f:
        f.write(file_hash)

    # 4. 生成徽章文件 badge.json
    generate_badge(logger)


# ==============================================================================
# 程序入口 (Main)
# ==============================================================================

if __name__ == "__main__":
    ensure_dir(OUTPUT_DIR)

    # 初始化
    logger = MergeLogger()

    # 获取数据
    upstream, upstream_ts = fetch_upstream(logger)
    custom, custom_ts = load_custom(logger)

    # 写入日志头
    logger.header(upstream_ts, custom_ts)

    # 处理逻辑
    final_data = process_rules(upstream, custom, logger)

    # 保存结果
    save_output(final_data, logger)

    # 结束
    logger.save()
    print(f"[ok] Log saved to {LOG_FILE}")
