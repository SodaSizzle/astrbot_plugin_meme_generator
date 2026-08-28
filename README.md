<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_meme_generator?name=astrbot_plugin_meme_generator&theme=gelbooru&padding=8&offset=0&align=top&scale=1&pixelated=0&darkmode=auto)

# AstrBot 表情包生成插件

**v2.3.0 · 关键词触发 · QQ 头像 · 自定义模板目录**

基于 [meme-generator-rs](https://github.com/MemeCrafters/meme-generator-rs) 的 AstrBot 表情包插件。

</div>

## 功能

- 发送模板关键词即可生成表情包。
- 支持 `@用户`、QQ 号、图片、文本和引用消息。
- 支持触发前缀、生成冷却、头像缓存和生成超时配置。
- 管理员可以禁用单个模板或停用整个插件。
- QQ 群：`771954725`
- 问题反馈：[GitHub Issues](https://github.com/SodaSizzle/astrbot_plugin_meme_generator/issues)


如果这个插件对你有帮助，欢迎点一个 Star。
## 生成效果示例

![表情包生成效果](static/picture/demo.png)

## 菜单预览

### 帮助菜单

![帮助菜单](static/picture/help.png)

### 模板目录

![模板目录](static/picture/list.png)

### 运行状态

![运行状态](static/picture/info.png)

## 安装

在 AstrBot 插件目录中克隆仓库并安装依赖：

```bash
cd AstrBot/data/plugins
git clone https://github.com/SodaSizzle/astrbot_plugin_meme_generator
pip install -r astrbot_plugin_meme_generator/requirements.txt
```

安装或更新后，请重载插件或重启 AstrBot。

## 使用方式

### 生成表情

```text
摸头
摸头 @某人
摸头 2352938756
举牌 你好世界
```

QQ 号必须作为独立参数填写，例如 `摸头 2352938756`。直接填写机器人自身 QQ 号同样有效。

如果配置了 `trigger_prefix`，则需要在关键词前添加该前缀。例如前缀为 `#`：

```text
#摸头 2352938756
```

不建议让插件的 `trigger_prefix` 与 AstrBot 全局唤醒前缀相同，否则消息可能先进入对话处理流程。

### 基础命令

| 命令 | 别名 | 说明 |
|---|---|---|
| `/表情帮助` | `/meme帮助`、`/meme菜单` | 查看新版帮助菜单 |
| `/表情列表 [页码]` | `/meme列表 [页码]` | 分页查看模板，每页 48 个 |
| `/表情信息 <关键词>` | `/meme信息 <关键词>` | 查看模板名称、别名、参数和标签 |
| `<关键词> [参数]` | — | 直接生成表情包 |

模板目录示例：

```text
/表情列表
/表情列表 2
/meme列表 3
```

目录卡片使用第一个可触发关键词作为标题，不再显示 `raise_sign`、`petpet` 等内部英文模板 key。

### 管理命令

以下命令仅 Bot 管理员可用：

| 命令 | 别名 | 说明 |
|---|---|---|
| `/单表情禁用 <模板名>` | `/单meme禁用 <模板名>` | 禁用指定模板 |
| `/单表情启用 <模板名>` | `/单meme启用 <模板名>` | 重新启用模板 |
| `/禁用列表` | — | 查看当前禁用模板 |
| `/表情启用` | `/meme启用` | 启用整个插件 |
| `/表情禁用` | `/meme禁用` | 禁用整个插件 |
| `/表情资源` | `/meme资源`、`/表情资源状态` | 查看资源初始化状态 |
| `/表情状态` | `/meme状态` | 查看运行状态和配置统计 |

## 资源目录

首次启动时，插件会自动下载资源到 AstrBot 分配的插件数据目录：

```text
AstrBot/
└── data/
    └── plugin_data/
        └── astrbot_plugin_meme_generator/
            ├── resources/
            │   ├── fonts/
            │   └── images/
            └── cache/
                └── meme_avatars/
```

Windows、Linux 和 Docker 均使用 AstrBot 分配的插件数据目录保存资源和头像缓存。新资源完整后，会清理旧的 `~/.meme_generator/resources/`；其他旧配置文件不会被删除。

自动下载失败时，可以从 [Releases](https://github.com/SodaSizzle/astrbot_plugin_meme_generator/releases) 下载资源包，并将完整的 `resources/` 解压到上述插件数据目录。

### Linux / Docker 字体

若生成图片出现方块或缺字，请安装中文字体：

```bash
apt update
apt install -y fontconfig fonts-noto-cjk
fc-cache -fv
```

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enable_plugin` | `bool` | `true` | 是否响应表情生成请求 |
| `trigger_prefix` | `string` | `""` | 表情关键词专用前缀 |
| `cooldown_seconds` | `int` | `3` | 单用户冷却时间，范围 0–60 秒 |
| `generation_timeout` | `int` | `30` | 单次生成超时，范围 5–120 秒 |
| `enable_avatar_cache` | `bool` | `true` | 是否缓存 QQ 头像 |
| `cache_expire_hours` | `int` | `24` | 头像缓存有效期，范围 1–168 小时 |
| `disabled_templates` | `list` | `[]` | 被管理员禁用的模板列表 |

## 外部模板

扩展额外表情资源请参考 meme-generator-rs Wiki：

- [加载其他表情](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E5%8A%A0%E8%BD%BD%E5%85%B6%E4%BB%96%E8%A1%A8%E6%83%85)
- [配置文件说明](https://github.com/MemeCrafters/meme-generator-rs/wiki/%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)

动态库放入本插件数据目录的 `libraries/`，对应图片与字体放入 `resources/`。
