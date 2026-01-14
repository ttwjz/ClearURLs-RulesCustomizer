import json
import requests
import copy
import yaml
import os

# ================= 配置区域 =================
# 上游规则地址
UPSTREAM_URL = "https://rules2.clearurls.xyz/data.minify.json"

# 输出目录和文件名
OUTPUT_DIR = "rules"
UPSTREAM_FILE = os.path.join(OUTPUT_DIR, "upstream_rules.json")  # 上游文件名
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "merged_rules.json")  # 合并结果文件名

# 自定义规则源文件
CUSTOM_FILE = "custom_rules.yaml"
# ===========================================

# 默认规则模板
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

# 需要处理为数组的字段
RULE_FIELDS = ["rules", "referralMarketing", "rawRules", "redirections"]
ARRAY_FIELDS = RULE_FIELDS + ["exceptions"]


def ensure_dir(directory):
    """确保输出目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)


def normalize_to_list(value):
    """
    将输入标准化为列表。
    支持：
    1. 列表: ['a', 'b'] -> ['a', 'b']
    2. 字符串: 'a b  c' -> ['a', 'b', 'c'] (按空白字符切分)
    """
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list):
        return value
    return []


def fetch_upstream():
    print(f"[-] Fetching upstream from {UPSTREAM_URL}...")
    try:
        r = requests.get(UPSTREAM_URL)
        r.raise_for_status()
        data = r.json()

        # 保存上游备份 (upstream_rules.json)
        print(f"[-] Saving upstream backup to {UPSTREAM_FILE}...")
        with open(UPSTREAM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        return data
    except Exception as e:
        print(f"[!] Error fetching upstream: {e}")
        exit(1)


def load_custom():
    print(f"[-] Loading custom rules from {CUSTOM_FILE}...")
    if not os.path.exists(CUSTOM_FILE):
        print("[!] No custom rules file found.")
        return {"blocklist": [], "providers": {}}

    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def process_rules(upstream_data, custom_data):
    print("[-] Processing rules...")
    providers = upstream_data.get("providers", {})
    blocklist = normalize_to_list(custom_data.get("blocklist", []))

    # 1. 执行 Blocklist 删除
    for key in blocklist:
        if key in providers:
            # print(f"    [Delete] {key}") # 日志太长可注释
            del providers[key]

    # 2. 执行新增/修改
    custom_providers = custom_data.get("providers", {}) or {}

    for name, patch_data in custom_providers.items():
        if not patch_data:
            continue

        if name not in providers:
            print(f"    [Add New] {name}")
            providers[name] = copy.deepcopy(DEFAULT_PROVIDER)
        else:
            print(f"    [Modify]  {name}")

        target = providers[name]

        for field, value in patch_data.items():
            # 预处理：如果是数组型字段，转为 List
            if field in ARRAY_FIELDS or field.startswith("del-"):
                value = normalize_to_list(value)

            # 逻辑 A: 删除指定规则 (del-rules, del-exceptions...)
            if field.startswith("del-"):
                target_field = field[4:]
                if target_field in ARRAY_FIELDS:
                    original_list = target.get(target_field, [])
                    target[target_field] = [x for x in original_list if x not in value]

            # 逻辑 B: 追加/合并数组
            elif field in ARRAY_FIELDS:
                original_list = target.get(field, [])
                new_set = set(original_list)
                new_set.update(value)
                target[field] = sorted(list(new_set))

            # 逻辑 C: 直接覆盖标量 (urlPattern 等)
            else:
                target[field] = value

        # 逻辑 D: 自动判断 completeProvider
        # 如果用户没有显式指定 completeProvider，且存在过滤规则，则设为 false
        if "completeProvider" not in patch_data:
            has_rules = any(len(target.get(f, [])) > 0 for f in RULE_FIELDS)
            if has_rules:
                target["completeProvider"] = False

    return {"providers": providers}


def save_output(data):
    print(f"[-] Saving final rules to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    ensure_dir(OUTPUT_DIR)
    upstream = fetch_upstream()
    custom = load_custom()
    final_data = process_rules(upstream, custom)
    save_output(final_data)
    print("[ok] Done.")
