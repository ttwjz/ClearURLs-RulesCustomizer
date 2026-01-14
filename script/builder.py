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
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "merged_rules.json")  # 人类可读版
MINIFIED_FILE = os.path.join(OUTPUT_DIR, "rules_min.json")  # 插件专用版(压缩)
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
        # 替换逗号为空格 -> 切分 -> 去除每项两端的引号
        items = value.replace(",", " ").split()
        return [item.strip("\"'") for item in items]
    if isinstance(value, list):
        return value
    return []


def format_http_date(date_str):
    if not date_str:
        return "Unknown"
    try:
        dt = parsedate_to_datetime(date_str)
        dt_cn = dt.astimezone(CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


def get_file_mtime(filepath):
    if os.path.exists(filepath):
        ts = os.path.getmtime(filepath)
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


def minify_data(data):
    """生成最小化的数据副本"""
    minified_providers = {}

    for name, provider in data.get("providers", {}).items():
        mini = {}

        # 1. urlPattern (必填)
        if "urlPattern" in provider:
            mini["urlPattern"] = provider["urlPattern"]

        # 2. completeProvider: 如果是 False，剔除 (保留 True)
        if provider.get("completeProvider") is True:
            mini["completeProvider"] = True

        # 3. forceRedirection: 如果是默认 False，剔除 (保留 True)
        if provider.get("forceRedirection") is True:
            mini["forceRedirection"] = True

        # 4. 数组字段: 如果为空，剔除
        for key in ARRAY_FIELDS:
            val = provider.get(key)
            if val and len(val) > 0:
                mini[key] = val

        minified_providers[name] = mini

    return {"providers": minified_providers}


def save_output(data, logger):
    # 1. 保存 Pretty 版本 (Merged Rules)
    logger.log(f"[-] Saving merged rules to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    # 2. 保存 Minified 版本 (Rules.min.json)
    logger.log("[-] Generating minified rules...")
    minified_data = minify_data(data)

    logger.log(f"[-] Saving minified rules to {MINIFIED_FILE}...")
    with open(MINIFIED_FILE, "w", encoding="utf-8") as f:
        # separators=(',', ':') 移除所有不必要的空格
        json.dump(
            minified_data, f, indent=None, separators=(",", ":"), ensure_ascii=False
        )


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
