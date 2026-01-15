# ClearURLs 规则构建产物 (Build Artifacts)

> ⚠️ **警告：此分支 (`gh-pages`) 由 GitHub Actions 自动构建生成。**
> 
> **请勿直接在此分支修改任何文件**，您的修改会在下次构建时被强制覆盖。
> 如需添加或修改规则，请前往 [main 分支](https://github.com/ttwjz/ClearURLs-RulesCustomizer) 编辑 `custom_rules.yaml` 并提交。

## 📂 文件下载

以下链接即为 **GitHub Pages CDN** 加速链接，请直接填入插件设置中。

| 文件用途 | 文件名 | **在线链接 (填入插件)** |
| :--- | :--- | :--- |
| **规则文件** | `rules.minify.json` | `https://ttwjz.github.io/ClearURLs-RulesCustomizer/rules.minify.json` |
| **校验文件** | `rules.minify.hash` | `https://ttwjz.github.io/ClearURLs-RulesCustomizer/rules.minify.hash` |

## 🔍 其他文件

*   **[merged_rules.json](merged_rules.json)**: 包含缩进格式的完整规则（方便人类阅读调试）。
*   **[upstream_rules.json](upstream_rules.json)**: 本次构建时拉取的上游规则备份。
*   **[merge_log.txt](merge_log.txt)**: 本次构建的详细日志（包含时间戳和冲突警告）。

## 🚀 插件设置方法

1.  打开浏览器上的 **ClearURLs** 插件图标。
2.  进入 **Settings (设置)** 。
3.  将上表中的 **在线链接** 复制并填入对应的输入框。
4.  点击 **"Save and restart plugin"**。

---
[返回源码仓库 (Go to Source Code)](https://github.com/ttwjz/ClearURLs-RulesCustomizer)