<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_meme_generator?name=astrbot_plugin_meme_generator&theme=gelbooru&padding=8&offset=0&align=top&scale=1&pixelated=0&darkmode=auto)

# 🎭 AstrBot 表情包生成器

_✨ 高性能智能表情包生成器 - 让聊天更有趣 ✨_

![Version](https://img.shields.io/badge/version-v2.0-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.11+-blue?style=for-the-badge)
![License](https://img.shields.io/badge/license-GNU%20GPL%20v3-green?style=for-the-badge)
![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-purple?style=for-the-badge)

</div>

## 📢 有问题可加入群聊

- q群：**771954725**

👉 [点击加入群聊](https://qun.qq.com/universal-share/share?ac=1&authKey=f6x7Z5%2FzsUwmoctYcMvLhdGw513QR2%2BFyIB8tJKMx50pEoGJRg3xsL8gf%2Bje9CgE&busi_data=eyJncm91cENvZGUiOiI3NzE5NTQ3MjUiLCJ0b2tlbiI6IlQwcWphdG5WL3pJZnpiVGxYaS9tRk13d2VWNW1JR3B0NnZoR1lnT3pkWTBMVTZUcXJybTM5QkVwZzFzSnlzTmoiLCJ1aW4iOiIxNTEyMDA0MjA1In0%3D&data=Us_H9b5JmURoPJSRIXD48XgD0oL5-HQjpcJQsXJ6zAIM_ujDXwWeNCstUSUDJkqbsDABFq4zmLn55KLlF_GsOw&svctype=4&tempid=h5_group_info)

## 🚀 项目简介

专为 **AstrBot** 打造的**智能表情包生成插件**，基于 [meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs) 与 [nonebot-plugin-memes](https://github.com/MemeCrafters/nonebot-plugin-memes) 开发。

**v2.0 新增**：**自动补图** —— 根据用户消息与 LLM 回复中的情绪信号，在对话结束后自动补发一张契合情境的表情包，无需额外调用 LLM。

### ✨ 核心特性

- 🖼️ **多源图片支持** - 自动获取用户头像、支持上传图片、引用消息图片
- ⚡ **高性能渲染** - 基于 Rust 底层引擎，生成速度极快
- 🎨 **丰富模板库** - 内置 200+ 精选表情包模板
- 🤖 **自动补图（v2.0）** - 本地规则识别情绪 → 概率决策 → 自动挑选合适表情补发；支持 3 档活跃度预设
- 🔧 **简洁配置** - 高级参数由档位综合调度，用户只需选"保守 / 平衡 / 活跃"
- 💾 **智能缓存** - 头像缓存机制，提升生成速度
- ⏱️ **冷却控制** - 冷却、单会话上限、情绪重复抑制，防刷屏

![img.png](static/picture/demo.png)

## 📦 快速安装

```bash
# 进入插件目录
cd astrBot/data/plugins

# 克隆项目
git clone https://github.com/SodaSizzle/astrbot_plugin_meme_generator

# 安装依赖
pip install -r astrbot_plugin_meme_generator/requirements.txt
```

### 🚀 资源初始化

> 💡 **重要提示**: 首次启动需要下载表情包模板资源，请耐心等待。

#### 自动下载（推荐）

插件首次启动时自动把资源下载到用户目录：
- **Windows**: `C:\Users\{用户名}\.meme_generator\`
- **Linux**: `~/.meme_generator/`

> 下载期间可在日志里看到 `⏳ 表情包资源初始化中 - 已耗时 N 秒` 的心跳，或在聊天里对 Bot 发送 `/表情资源` 查看当前状态。

#### 手动下载（网络较慢时使用）

**下载地址**: https://github.com/SodaSizzle/astrbot_plugin_meme_generator/releases

##### Windows
```bash
# 1. 下载 resources.zip
# 2. 解压到 C:\Users\{你的用户名}\.meme_generator\ 目录下
```

##### Linux
```bash
# 1. 下载 resources.tar.gz
# 2. 解压到指定目录
tar -zxvf resources.tar.gz -C ~/.meme_generator/
```

##### Docker
```bash
docker cp resources.tar.gz astrbot:/root/.meme_generator/
docker exec -it astrbot tar -zxvf /root/.meme_generator/resources.tar.gz -C /
docker restart astrbot
```

### ⚠️ 字体问题解决

表情包中的文字出现乱码或方块时：

```bash
# Linux / Docker
export LANG=en_US.UTF-8
# 重启 AstrBot
```

#### 验证资源
```
.meme_generator/
└── resources/
    ├── fonts/     # 字体文件
    └── images/    # 图片资源
```

## 🎨 添加额外资源

> 📖 [加载其他表情 - meme-generator-rs Wiki](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E5%8A%A0%E8%BD%BD%E5%85%B6%E4%BB%96%E8%A1%A8%E6%83%85)

1. 在 [配置文件](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6) 中把 `load_external_memes` 设成 `true`
2. 把额外仓库编译的 **动态链接库** 放到 `$MEME_HOME/libraries/`
3. 把图片/字体放到 `$MEME_HOME/resources/`

动态链接库下载：[meme-generator-contrib-rs Actions](https://github.com/MemeCrafters/meme-generator-contrib-rs/actions)

### 🐛 Fontconfig 错误

```bash
apt update && apt install -y fontconfig fonts-dejavu-core
fc-cache -fv
```

## ⚙️ 配置说明

### 基础配置

| 配置项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enable_plugin` | bool | `true` | 全局插件开关 |
| `cooldown_seconds` | int | `3` | 用户触发间隔（秒） |
| `disabled_templates` | list | `[]` | 禁用的模板列表 |

### 🤖 自动补图配置（v2.0 新增）

| 配置项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enable_auto_meme` | bool | `false` | 启用自动补图 |
| `auto_meme_scope` | enum | `all` | 生效范围：`all` / `group` / `private` |
| `auto_meme_level` | enum | `平衡` | 活跃度档位：`保守` / `平衡` / `活跃` |

**档位内部参数（不暴露给用户，由档位一键切换）：**

| 档位 | 基础概率 | 冷却 | 单对话上限 |
|---|---|---|---|
| 保守 | 15% | 5 分钟 | 1 张 |
| **平衡**（默认） | 35% | 2 分钟 | 1 张 |
| 活跃 | 55% | 1 分钟 | 2 张 |

> 💡 **活跃度是"情绪门槛"而不是"发图频率"**：保守档只在情绪非常明显时才发；活跃档稍微有点情绪就发。没匹配到情绪时任何档位都不会发。

### 工作流程

```
用户 → LLM 回复 → ① 本地情绪识别 → ② 概率掷骰（含场景/情绪/历史加减）
                                                ↓
                ← 冷却/上限检查 ← ③ 从模板池挑选契合的候选
```

整个流程**不额外调用 LLM**，纯本地规则与概率决策。

## 📋 命令列表

### 🎮 基础命令

<div align="center">

![表情帮助命令效果图](static/picture/help.png)

</div>

| 命令 | 功能 | 示例 |
|---|---|---|
| `表情帮助` | 查看功能菜单 | `表情帮助` / `meme帮助` |
| `表情列表` | 浏览所有模板 | `表情列表` / `meme列表` |
| `表情信息 <关键词>` | 查看模板详情 | `表情信息 摸头` |
| `<关键词> [参数]` | 生成表情包 | `摸头 @某人` / `举牌 你好世界` |

<div align="center">

![表情列表命令效果图](static/picture/list.png)

</div>

### 🔧 管理命令（仅 Bot 管理员）

<div align="center">

![表情状态命令效果图](static/picture/info.png)

</div>

| 命令 | 功能 | 示例 |
|---|---|---|
| `表情启用` / `表情禁用` | 整个插件开关 | `表情启用` |
| `表情状态` | 插件详细信息和统计 | `表情状态` |
| `表情资源` | **（v2.0）** 查看资源下载 / 就绪状态 | `表情资源` |
| `单表情禁用 <模板名>` | 禁用指定模板 | `单表情禁用 摸头` |
| `单表情启用 <模板名>` | 启用指定模板 | `单表情启用 摸头` |
| `禁用列表` | 查看禁用模板 | `禁用列表` |

## 🎯 快速上手

### 基础使用
```
表情帮助              # 功能菜单
表情列表              # 浏览模板
摸头 @用户            # 生成
举牌 你好世界         # 文字表情包
```

### 启用自动补图
1. 在配置中打开 `enable_auto_meme = true`
2. 选择 `auto_meme_level`：保守（低频）/ 平衡（推荐）/ 活跃（高频）
3. 正常和 Bot 对话，AstrBot 回复后会**按概率**补一张情绪契合的表情包

### 管理功能
```
表情资源              # 看资源是否就绪
表情状态              # 看运行状态
单表情禁用 模板名      # 临时禁用单个模板
表情禁用              # 整个插件停用
```

## 🔧 技术架构

### 自动补图决策链

| 阶段 | 作用 |
|---|---|
| **情绪识别** | 1100+ 关键词 / 30+ emoji / 20+ 正则模式，双维度（场景+情绪）打分 |
| **概率合成** | 基础概率 + 信号强度 / 回复长度 / 模板风险 / 历史重复 / 近期发送等 7 项加减 |
| **模板筛选** | 从模板池按 `emotion_tags` / `scene_tags` / `auto_weight` / `risk_level` 挑 Top 5 |
| **硬阻断** | 代码块、命令、路径等技术性内容自动跳过 |

### 核心依赖

- **[meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs)** - Rust 高性能表情包生成引擎
- **[nonebot-plugin-memes](https://github.com/MemeCrafters/nonebot-plugin-memes)** - 模板资源和算法参考
- **AstrBot** - 机器人框架

## 📝 v2.0 更新亮点

- 🆕 **自动补图**：LLM 回复后按本地情绪规则自动补一张表情
- 🆕 **活跃度档位**：一个选项搞定所有自动补图参数，避免过度暴露
- 🆕 **`/表情资源`**：查看资源初始化状态，解决首次启动"不知道在干嘛"
- 🧹 **配置精简**：用户可调项从 13 个缩到 6 个，其余由系统综合
- 🧹 **关键词大幅扩充**：场景词 272 条，情绪词 346 条，用户提示 261 条
- 🔁 **决策机制升级**：硬阈值 → 概率掷骰（更自然、更"偶尔惊喜"）

## ❤️ 致谢

- [meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs) - 高性能表情包引擎
- [nonebot-plugin-memes](https://github.com/MemeCrafters/nonebot-plugin-memes) - 模板和算法参考
- [AstrBot](https://github.com/Soulter/AstrBot) - 机器人框架
- [astrbot_plugin_LetAI_sendemojis](https://github.com/Heyh520/astrbot_plugin_LetAI_sendemojis) - 自动补图的概率决策思路

---

<div align="center">

**🎉 感谢使用 AstrBot 表情包生成器！**

如果觉得好用，请给个 ⭐ Star 支持一下！

</div>
