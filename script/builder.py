import json
import requests
import copy
import yaml
import os

# ================= 配置区域 =================
UPSTREAM_URL = (
    "https://gitlab.com/Kevin Roebert/ClearURLs/raw/master/data/data.min.json"
)
OUTPUT_DIR = "rules"
UPSTREAM_FILE = os.path.join(OUTPUT_DIR, "upstream_rules.json")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "merged_rules.json")
CUSTOM_FILE = "custom_rules.yaml"
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


def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def normalize_to_list(value):
    """
    将输入标准化为列表。
    1. 列表: 直接返回
    2. 字符串:
       - 将所有逗号(,)替换为空格
       - 按空白字符(空格、换行、Tab)切分
       - 自动去除空项
    """
    if isinstance(value, str):
        # 核心修改：允许逗号作为分隔符 (先转为空格，再交给 split 处理)
        return value.replace(",", " ").split()
    if isinstance(value, list):
        return value
    return []


def fetch_upstream():
    print(f"[-] Fetching upstream from {UPSTREAM_URL}...")
    try:
        r = requests.get(UPSTREAM_URL)
        r.raise_for_status()
        data = r.json()

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
        return {}

    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def upsert_provider(providers, name, patch_data, section_name):
    """
    统一处理 新增(Add) 和 修改(Modify) 的逻辑
    """
    if not patch_data:
        return

    exists = name in providers

    if not exists:
        action_log = "[Create]"
        if section_name == "modify-providers":
            action_log += " (from modify section)"
        providers[name] = copy.deepcopy(DEFAULT_PROVIDER)
    else:
        action_log = "[Merge]"
        if section_name == "add-providers":
            action_log += " (from add section)"

    print(f"    {action_log:<30} {name}")

    target = providers[name]

    for field, value in patch_data.items():
        if field in ARRAY_FIELDS or field.startswith("del-"):
            value = normalize_to_list(value)

        if field.startswith("del-"):
            target_field = field[4:]
            if target_field in ARRAY_FIELDS:
                original_list = target.get(target_field, [])
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


def process_rules(upstream_data, custom_data):
    print("[-] Processing rules...")
    providers = upstream_data.get("providers", {})

    # 1. Del-Providers (支持字符串+逗号)
    del_list = normalize_to_list(custom_data.get("del-providers", []))
    for name in del_list:
        if name in providers:
            # print(f"    [Delete] {name}")
            del providers[name]

    # 2. Add-Providers
    add_dict = custom_data.get("add-providers", {}) or {}
    for name, patch in add_dict.items():
        upsert_provider(providers, name, patch, "add-providers")

    # 3. Modify-Providers
    mod_dict = custom_data.get("modify-providers", {}) or {}
    for name, patch in mod_dict.items():
        upsert_provider(providers, name, patch, "modify-providers")

    return {"providers": providers}


def save_output(data):
    print(f"[-] Saving merged rules to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    ensure_dir(OUTPUT_DIR)
    upstream = fetch_upstream()
    custom = load_custom()
    final_data = process_rules(upstream, custom)
    save_output(final_data)
    print("[ok] Done.")
