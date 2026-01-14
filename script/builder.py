import json
import requests
import copy
import yaml
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ================= 配置区域 =================
UPSTREAM_URL = "https://rules2.clearurls.xyz/data.minify.json"
OUTPUT_DIR = "rules"
UPSTREAM_FILE = os.path.join(OUTPUT_DIR, "upstream_rules.json")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "merged_rules.json")
LOG_FILE = os.path.join(OUTPUT_DIR, "merge_log.txt")
CUSTOM_FILE = "custom_rules.yaml"

# 定义北京时区 (UTC+8)
CN_TZ = timezone(timedelta(hours=8))
# ===========================================

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

RULE_FIELDS = ["rules", "referralMarketing", "rawRules", "redirections"]
ARRAY_FIELDS = RULE_FIELDS + ["exceptions"]


class MergeLogger:
    def __init__(self):
        self.lines = []
        self.warnings = []

    def log(self, message):
        print(message)
        self.lines.append(message)

    def warn(self, message):
        print(f"\033[93m{message}\033[0m")
        self.warnings.append(message)
        self.lines.append(message)

    def header(self, upstream_ts, custom_ts):
        # 获取当前北京时间
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
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))
            if self.warnings:
                f.write("\n\n" + "=" * 40 + "\n")
                f.write(f"WARNING SUMMARY ({len(self.warnings)})\n")
                f.write("=" * 40 + "\n")
                f.write("\n".join(self.warnings))


def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def normalize_to_list(value):
    if isinstance(value, str):
        return value.replace(",", " ").split()
    if isinstance(value, list):
        return value
    return []


def format_http_date(date_str):
    """将 HTTP 头时间转换为北京时间字符串"""
    if not date_str:
        return "Unknown"
    try:
        # 1. 解析 RFC 1123 格式 (得到的是带时区的 datetime, 通常是 GMT)
        dt = parsedate_to_datetime(date_str)
        # 2. 转换为北京时间
        dt_cn = dt.astimezone(CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


def get_file_mtime(filepath):
    """获取文件修改时间并转换为北京时间字符串"""
    if os.path.exists(filepath):
        ts = os.path.getmtime(filepath)
        # 将时间戳转换为北京时间
        dt_cn = datetime.fromtimestamp(ts, CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    return "N/A (File not found)"


def fetch_upstream(logger):
    logger.log(f"[-] Fetching upstream from {UPSTREAM_URL}...")
    try:
        r = requests.get(UPSTREAM_URL)
        r.raise_for_status()

        raw_date = r.headers.get("Last-Modified")
        formatted_date = format_http_date(raw_date)

        data = r.json()

        logger.log(f"[-] Saving upstream backup to {UPSTREAM_FILE}...")
        with open(UPSTREAM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        return data, formatted_date
    except Exception as e:
        logger.log(f"[!] Error fetching upstream: {e}")
        exit(1)


def load_custom(logger):
    logger.log(f"[-] Loading custom rules from {CUSTOM_FILE}...")
    custom_ts = get_file_mtime(CUSTOM_FILE)

    if not os.path.exists(CUSTOM_FILE):
        logger.warn("[!] No custom rules file found.")
        return {}, custom_ts

    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}), custom_ts


def upsert_provider(providers, name, patch_data, section_name, logger):
    if not patch_data:
        return

    exists = name in providers
    action_type = ""

    if section_name == "add-providers":
        if exists:
            logger.warn(
                f"    [WARN] Duplicate Add: '{name}' already exists in upstream. Applying as Merge."
            )
            action_type = "Merge (Duplicate Add)"
        else:
            action_type = "Create"

    elif section_name == "modify-providers":
        if not exists:
            logger.warn(
                f"    [WARN] Missing Modify: '{name}' not found in upstream. Applying as Create."
            )
            action_type = "Create (Missing Modify)"
            providers[name] = copy.deepcopy(DEFAULT_PROVIDER)
        else:
            action_type = "Modify"

    if name not in providers:
        providers[name] = copy.deepcopy(DEFAULT_PROVIDER)

    if "WARN" not in action_type:
        logger.log(f"    [{action_type:<6}] {name}")

    target = providers[name]

    for field, value in patch_data.items():
        if field in ARRAY_FIELDS or field.startswith("del-"):
            value = normalize_to_list(value)

        if field.startswith("del-"):
            target_field = field[4:]
            if target_field in ARRAY_FIELDS:
                original_list = target.get(target_field, [])

                not_found_items = [x for x in value if x not in original_list]
                if not_found_items:
                    logger.warn(
                        f"        [WARN] '{name}': Trying to delete non-existent {target_field}: {not_found_items}"
                    )

                target[target_field] = [x for x in original_list if x not in value]

        elif field in ARRAY_FIELDS:
            original_list = target.get(field, [])
            new_set = set(original_list)
            new_set.update(value)
            target[field] = sorted(list(new_set))

        else:
            target[field] = value

    if "completeProvider" not in patch_data:
        has_rules = any(len(target.get(f, [])) > 0 for f in RULE_FIELDS)
        if has_rules:
            target["completeProvider"] = False


def process_rules(upstream_data, custom_data, logger):
    logger.log("[-] Processing rules...")
    providers = upstream_data.get("providers", {})

    # 1. Del
    del_list = normalize_to_list(custom_data.get("del-providers", []))
    for name in del_list:
        if name in providers:
            logger.log(f"    [Delete] {name}")
            del providers[name]
        else:
            logger.warn(
                f"    [WARN] Delete failed: Provider '{name}' not found in upstream."
            )

    # 2. Add
    add_dict = custom_data.get("add-providers", {}) or {}
    for name, patch in add_dict.items():
        upsert_provider(providers, name, patch, "add-providers", logger)

    # 3. Modify
    mod_dict = custom_data.get("modify-providers", {}) or {}
    for name, patch in mod_dict.items():
        upsert_provider(providers, name, patch, "modify-providers", logger)

    return {"providers": providers}


def save_output(data, logger):
    logger.log(f"[-] Saving merged rules to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    ensure_dir(OUTPUT_DIR)

    logger = MergeLogger()

    upstream, upstream_ts = fetch_upstream(logger)
    custom, custom_ts = load_custom(logger)

    logger.header(upstream_ts, custom_ts)

    final_data = process_rules(upstream, custom, logger)
    save_output(final_data, logger)

    logger.save()
    print(f"[ok] Log saved to {LOG_FILE}")
