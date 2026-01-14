import json
import requests
import copy
import yaml
import os

# ================= 配置区域 =================
UPSTREAM_URL = "https://rules2.clearurls.xyz/data.minify.json"
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
    """将字符串按空格切分为列表，如果是列表则直接返回"""
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
    providers: 总规则字典
    name: 厂商名称
    patch_data: 自定义数据
    section_name: 当前来源 ('add-providers' 或 'modify-providers')，仅用于日志区分
    """
    if not patch_data:
        return

    exists = name in providers

    # 日志逻辑：根据实际情况显示操作，而不是看它在 yaml 的哪个区
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
        # 预处理：转列表
        if field in ARRAY_FIELDS or field.startswith("del-"):
            value = normalize_to_list(value)

        # 逻辑 1: 删除列表中的指定项 (del-rules, del-exceptions...)
        if field.startswith("del-"):
            target_field = field[4:]
            if target_field in ARRAY_FIELDS:
                original_list = target.get(target_field, [])
                target[target_field] = [x for x in original_list if x not in value]

        # 逻辑 2: 追加列表 (合并去重)
        elif field in ARRAY_FIELDS:
            original_list = target.get(field, [])
            new_set = set(original_list)
            new_set.update(value)
            target[field] = sorted(list(new_set))

        # 逻辑 3: 标量直接覆盖
        else:
            target[field] = value

    # 逻辑 4: 自动推断 completeProvider
    if "completeProvider" not in patch_data:
        has_rules = any(len(target.get(f, [])) > 0 for f in RULE_FIELDS)
        if has_rules:
            target["completeProvider"] = False


def process_rules(upstream_data, custom_data):
    print("[-] Processing rules...")
    providers = upstream_data.get("providers", {})

    # 1. 处理删除 (Del-Providers)
    del_list = normalize_to_list(custom_data.get("del-providers", []))
    for name in del_list:
        if name in providers:
            # print(f"    [Delete] {name}")
            del providers[name]

    # 2. 处理新增 (Add-Providers)
    # 即使已存在，也会按照 upsert 逻辑合并
    add_dict = custom_data.get("add-providers", {}) or {}
    for name, patch in add_dict.items():
        upsert_provider(providers, name, patch, "add-providers")

    # 3. 处理修改 (Modify-Providers)
    # 即使不存在，也会按照 upsert 逻辑新建
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
