<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_meme_generator?name=astrbot_plugin_meme_generator&theme=gelbooru&padding=8&offset=0&align=top&scale=1&pixelated=0&darkmode=auto)

# AstrBot 表情包生成插件

基于 [meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs) 的 AstrBot 表情包插件。支持关键词触发、模板查询、管理员禁用模板，以及基于本地规则的自动补图。

</div>

## 功能概览

- 直接发送关键词即可生成表情包
- 支持 `@用户`、文本、图片、引用消息等常见输入
- 提供模板列表、模板详情、资源状态、插件状态等查询命令
- 支持单模板禁用/启用，方便群聊内容管理
- 支持头像缓存、触发前缀、自定义冷却时间
- 支持自动补图，不额外调用 LLM

## 交流与反馈

- QQ 群：`771954725`

## 效果预览

![插件预览](static/picture/demo.png)

## 安装

```bash
# 进入 AstrBot 插件目录
cd astrBot/data/plugins

# 克隆本仓库
git clone https://github.com/SodaSizzle/astrbot_plugin_meme_generator

# 安装依赖
pip install -r astrbot_plugin_meme_generator/requirements.txt
```

## 首次启动与资源初始化

首次启动时，插件会自动检查并下载表情包资源。资源未准备完成前，生成命令可能暂时不可用，这是正常现象。

### 自动下载

默认会把资源下载到用户目录下：

- Windows: `C:\Users\{用户名}\.meme_generator\`
- Linux: `~/.meme_generator/`
- Docker: `/root/.meme_generator/`

### 手动下载

如果网络较慢或自动下载失败，可以手动下载资源包：

- 下载地址: <https://github.com/SodaSizzle/astrbot_plugin_meme_generator/releases>

Windows:

```bash
# 1. 下载 resources.zip
# 2. 解压到 C:\Users\{你的用户名}\.meme_generator\
```

Linux:

```bash
# 1. 下载 resources.tar.gz
# 2. 解压到 ~/.meme_generator/
tar -zxvf resources.tar.gz -C ~/.meme_generator/
```

Docker:

```bash
docker cp resources.tar.gz astrbot:/root/.meme_generator/
docker exec -it astrbot tar -zxvf /root/.meme_generator/resources.tar.gz -C /
docker restart astrbot
```

### 资源目录示例

```text
.meme_generator/
└── resources/
    ├── fonts/
    └── images/
```

### 常见字体问题

如果生成结果中的文字出现乱码、方块或缺字，通常是运行环境缺少字体或语言环境未配置完整：

```bash
# Linux / Docker
export LANG=en_US.UTF-8
```

仍有问题时，可继续安装字体与 fontconfig：

```bash
apt update && apt install -y fontconfig fonts-noto-cjk && fc-cache -fv
```

## 使用方式

### 基础命令

<div align="center">

![帮助菜单](static/picture/help.png)

</div>

| 命令 | 别名 | 说明 |
|---|---|---|
| `表情帮助` | `meme帮助`、`meme菜单` | 查看帮助菜单 |
| `表情列表` | `meme列表` | 查看全部可用模板 |
| `表情信息 <关键词>` | `meme信息 <关键词>` | 查看指定模板详情 |
| `<关键词> [参数]` | 无 | 直接生成表情包 |

示例：

```text
摸头 @某人
举牌 你好世界
/摸头 @某人
```

如果你配置了 `trigger_prefix`，则需要携带此前缀触发，例如设置为 `/` 后，需要发送 `/摸头`。

建议不要把 `trigger_prefix` 设置成和 AstrBot 全局 `wake_prefix` 一样的值，尤其不要直接复用 `/`。否则消息可能会先进入 AstrBot 的唤醒或对话流程，导致表情指令无法按预期由本插件处理。

<div align="center">

![模板列表](static/picture/list.png)

</div>

### 管理命令

以下命令仅 Bot 管理员可用：

| 命令 | 别名 | 说明 |
|---|---|---|
| `单表情禁用 <模板名>` | `单meme禁用 <模板名>` | 禁用某个模板 |
| `单表情启用 <模板名>` | `单meme启用 <模板名>` | 重新启用某个模板 |
| `禁用列表` | 无 | 查看当前禁用模板列表 |
| `表情启用` | `meme启用` | 启用整个插件 |
| `表情禁用` | `meme禁用` | 禁用整个插件 |
| `表情资源` | `meme资源`、`表情资源状态` | 查看资源初始化状态 |
| `表情状态` | `meme状态` | 查看插件运行状态 |

<div align="center">

![状态面板](static/picture/info.png)

</div>

## 配置说明

### 基础配置

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enable_plugin` | `bool` | `true` | 全局插件开关 |
| `trigger_prefix` | `string` | `""` | 表情触发前缀，留空表示直接发关键词即可；建议不要与 AstrBot 全局唤醒前缀相同 |
| `cooldown_seconds` | `int` | `3` | 单个用户的生成冷却时间，范围 `0-60` 秒 |
| `generation_timeout` | `int` | `30` | 单次生成超时，范围 `5-120` 秒 |
| `enable_avatar_cache` | `bool` | `true` | 是否启用头像缓存 |
| `cache_expire_hours` | `int` | `24` | 头像缓存过期时间，范围 `1-168` 小时 |
| `disabled_templates` | `list` | `[]` | 禁用模板列表 |

前缀配置建议：

- 推荐使用与 AstrBot 全局 `wake_prefix` 不同的前缀，例如 `#`、`.`、`表情`
- 不推荐将 `trigger_prefix` 设置为 `/`。如果 AstrBot 也使用 `/` 作为唤醒前缀，消息可能会优先进入对话流程

### 自动补图配置

自动补图会在 AstrBot 正常回复后，根据用户消息和机器人回复做本地判断，决定是否额外发送一张表情图。整个流程不额外调用 LLM。

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enable_auto_meme` | `bool` | `false` | 是否启用自动补图 |
| `auto_meme_scope` | `string` | `all` | 生效范围：`all` / `group` / `private` |
| `auto_meme_level` | `string` | `平衡` | 活跃度：`保守` / `平衡` / `活跃` |

## 扩展额外资源

如果你需要加载额外的表情包资源，可以参考 `meme-generator-rs` 官方 Wiki：

- [加载其他表情](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E5%8A%A0%E8%BD%BD%E5%85%B6%E4%BB%96%E8%A1%A8%E6%83%85)
- [配置文件说明](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)

基本步骤：

1. 在配置文件中把 `load_external_memes` 设为 `true`
2. 将额外仓库编译得到的动态链接库放到 `$MEME_HOME/libraries/`
3. 将图片与字体资源放到 `$MEME_HOME/resources/`

动态链接库可参考：

- [meme-generator-contrib-rs Actions](https://github.com/MemeCrafters/meme-generator-contrib-rs/actions)

## 依赖项目

- [meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs)
- AstrBot

如果这个插件对你有帮助，欢迎点一个 Star。
