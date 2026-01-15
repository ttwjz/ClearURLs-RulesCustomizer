# ClearURLs-RulesCustomizer (ClearURLs 规则定制器)

[![Build ClearURLs Rules](https://github.com/ttwjz/ClearURLs-RulesCustomizer/actions/workflows/build_rules.yml/badge.svg)](https://github.com/ttwjz/ClearURLs-RulesCustomizer/actions/workflows/build_rules.yml)
[![Rules Updated](https://img.shields.io/endpoint?url=https://ttwjz.github.io/ClearURLs-RulesCustomizer/rules/badge.json)](https://github.com/ttwjz/ClearURLs-RulesCustomizer/commits/main)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**ClearURLs-RulesCustomizer** 是一个用于自动化构建 [ClearURLs](https://gitlab.com/ClearURLs/ClearURLs) 扩展规则的工具。

本项目以 ClearURLs 官方的上游规则为基准，通过 GitHub Actions 每日自动同步，并合并本地维护的 `custom_rules.yaml`，最终生成适用于插件的 `rules.min.json` 及其校验哈希。

> 🌏 **特别说明**：本仓库默认维护了一份**适用于中国🇨🇳用户的增强规则**，针对 **Baidu (百度)**、**Bing CN (必应中国)**、**Sogou (搜狗)** 等国内常用网站进行了深度的参数清理优化。

---

## 🚀 快速使用

如果你只想使用本项目生成的增强规则，请在浏览器插件中进行如下设置：

1.  点击浏览器工具栏的 **ClearURLs** 图标，进入 **设置 (Settings)** 。
2.  分别在自定义规则输入框中填入以下链接：

*   **data.json 档的网址 (规则)** :
    ```text
    https://ttwjz.github.io/ClearURLs-RulesCustomizer/rules/rules.min.json
    ```
*   **rules.hash 档的网址 (校验)** :
    ```text
    https://ttwjz.github.io/ClearURLs-RulesCustomizer/rules/rules.min.hash
    ```
4.  点击 **"储存并重启插件"**。

---

## ✨ 项目特性

*   **自动同步**：每天定时拉取 ClearURLs 上游最新规则，确保基准规则不过时。
*   **安全校验**：严格校验上游文件的 SHA256 哈希，防止供应链污染。
*   **配置简化**：使用易读的 `YAML` 格式替代复杂的 JSON，支持注释和多行文本块。
*   **智能合并**：
    *   支持 **Add (新增)**、**Modify (修改)**、**Delete (删除)** 三种模式。
    *   支持 **Append (追加)**、**Reset (覆盖)**、**Remove (移除)** 字段级操作。
    *   自动处理正则表达式的转义问题（区分手写正则与复制正则）。
*   **体积优化**：自动生成 Minified 版本，移除无用字段，节省带宽。

---

## 🛠️ 如何维护/贡献规则

本项目核心配置文件为 `custom_rules.yaml`。我们非常欢迎你提交 Pull Request 来完善国内网站的规则！

### 文件结构

```text
.
├── .github/workflows/  # CI/CD 自动化配置
├── script/             # Python 构建脚本
├── rules/              # (自动生成) 最终产物，包含 min.json 和 hash
├── custom_rules.yaml   # ✅ 在这里编辑自定义规则
└── README.md
```

### `custom_rules.yaml` 编写指南

配置文件分为三个主要区域，详细语法请参考文件内的注释文档。

#### 1. 新增规则 (add-providers)
用于添加上游不存在的网站规则。

```yaml
add-providers:
  example_site:
    # 推荐使用单引号包裹手写的正则表达式 (Raw String)
    urlPattern: '^https?:\/\/example\.com'
    rules:
      - 'utm_source'
      - 'token'
```

#### 2. 修改规则 (modify-providers)
用于修改上游已有的规则。

```yaml
modify-providers:
  google:
    # 默认行为是追加 (Append)
    rules:
      - 'new_tracking_param'
    
    # 使用 del- 前缀删除原有参数
    del-rules:
      - 'ved'
```

#### 3. 删除规则 (del-providers)
用于彻底移除某个网站的规则。

```yaml
del-providers:
  - doubleclick
```

### 正则表达式注意事项

*   **手写正则**：请使用 **单引号** (`'...'`)，无需双重转义。
    *   例：`'^https?:\/\/baidu\.com'`
*   **复制正则**：如果是从 `rules.json` 源文件中复制的（带有 `\\`），请使用 **双引号** (`"..."`)。
    *   例：`"^https?:\\\\/\\\\/baidu\\\\.com"`

---

## ⚙️ 自行部署

如果你希望维护自己的私有规则集：

1.  **Fork** 本仓库。
2.  修改 `custom_rules.yaml`。
3.  进入仓库 **Settings** -> **Pages**。
4.  将 **Source** 设置为 `Deploy from a branch`，分支选择 `main`，文件夹选择 `/ (root)`。
5.  保存后，GitHub Actions 会在下次运行时自动部署规则到你的 Pages 地址。

---

## 📄 许可证与致谢

本项目基于 GPLv3 许可证开源。

*   **核心逻辑**：基于 [Kevin Roebert](https://gitlab.com/KevinRoebert) 的 [ClearURLs](https://gitlab.com/ClearURLs/ClearURLs) 项目。
*   **上游规则**：[ClearURLs Rules](https://gitlab.com/ClearURLs/rules)。

ClearURLs is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.