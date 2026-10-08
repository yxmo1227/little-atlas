# Little Atlas · 云端笔记本

## 最新版：网页版

**[打开 Little Atlas](https://little-atlas-notebook.c8fmkxqy6h.chatgpt.site/)**

用邮箱注册自己的私人 **Notebook**。输入内容后点击 **＋**，进入可持续编辑的文章页面；首次标题和分类会自动生成，也可以自行修改。界面使用英文，支持中文或英文输入。

- 输入一个主题或整段内容，联网查找有来源的英文资料。
- 文章支持段落、标题和小标题；左侧文档大纲可以点击跳转，之后随时重新打开并增删内容。
- 编辑后自动保存到账号的云端；在电脑、手机或 iPad 登录同一账号，可以打开之前保存的笔记。
- 自动保存显示实际保存状态；两个设备同时编辑时会提示冲突并保留当前草稿，避免悄悄覆盖较新的内容。
- 保存内容后自动寻找相关图片；以前没有图片的词条重新打开时也会补图，并保留图片来源、作者和许可。
- 用选择笔留下需要的文字，用黄色荧光笔和红笔标注重点。
- 选取的研究资料可以直接追加到正在打开的文章，保留原有小标题、标题和分类；也支持导出 Markdown。
- 默认搜索、自动归类和配图不调用 AI 模型，不消耗模型 token。
- 每个账号从空白笔记本开始，已保存的文章、图片和标注只对该账号可见。

最新版已验证文档小标题和分类保存、跨会话编辑、旧版本冲突提示、长文章，以及不同账号之间的数据隔离。

网页版源码、安装步骤和检查命令见 **[web/README.md](web/README.md)**。邮箱目前作为登录名，尚未配置邮件验证和密码重置邮件。

| 目录 | 内容 |
| --- | --- |
| `web/` | 最新网页版：云端笔记、文档大纲、账号、联网搜索和自动配图 |
| `dictionary_app/` | Windows 本地桌面版 |
| `tests/` | 桌面版检查；网页版检查在 `web/tests/` |

下面是 Windows 桌面版的使用说明。

## Windows 本地桌面版

Little Atlas 是一款 Windows 本地桌面软件。输入今天学到的中文或英文主题，查看有来源的英文补充资料，再用笔划出你真正想留下的内容。词条按章节编成自己的字典。每个人第一次打开时都是空白的，个人数据留在自己的电脑上。

## 使用

1. 解压完整的 `LittleAtlas-Windows.zip`，双击 `LittleAtlas.exe`。不要单独移走 EXE；它需要旁边的 `_internal` 文件夹。
2. 在唯一的输入框中写中文或英文，按 Enter 或点击搜索键。软件会在默认浏览器打开 Google 搜索（默认浏览器是 Chrome 时便在 Chrome 打开），同时用 Wikimedia 公共资料在软件里提供带来源的英文建议。**默认搜索不调用 ChatGPT，不消耗模型用量。** Shift + Enter 换行。
3. 如果 Google 找到了更合适的英文文章，打开那篇文章，把文章自己的 HTTPS 链接粘贴进输入框并搜索。软件会抽取可选取的英文原文，保留文章链接作为来源。Google 搜索结果页本身不会自动回传到软件。
4. 搜索结果标题旁有三支笔：**选择笔**拖过的英文才会进入字典；**黄色荧光笔**和**红笔**用来标注重点，不会单独添加内容。按 Ctrl + Z 撤销上一笔。核对资料来源、章节和图片后，点击输入框里的 **＋** 保存。没有搜索结果时，＋可手动新建英文词条。
5. 麦克风可选择中文或 English 录音。再次点击后转成可编辑文字，检查无误再搜索。按 **Ctrl + B**，或右键点击搜索键并选 **Contents**，打开已收藏的章节与词条。正文可继续编辑、标注和自动保存。

首页只有一个较大的输入框，没有额外的大边框、目录按钮、每日画风或装饰背景。软件界面的按钮和提示使用英文，仍支持中文主题和中文语音。

## 联网研究与隐私

默认搜索会把搜索词交给 Google 搜索页面，以及 Wikipedia/Wikidata/Wikimedia Commons 的公开接口；无需 ChatGPT 登录或 API key。直接输入一篇文章的 HTTPS 链接时，软件会读取该公开网页的英文内容。它不会自动抓取 Google 的搜索结果列表：Google 的 [Custom Search JSON API](https://developers.google.com/custom-search/v1/overview)对新用户已关闭，普通浏览器打开搜索页也不会把结果传回桌面程序。

可选的 **ChatGPT research** 只会在你右键点击搜索键、明确选择它后运行。此功能用 [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart) 授权自己的账号；软件不会读取 Codex Desktop 的登录文件，也不包含共享 API 密钥。令牌保存在 Windows 凭据管理器中。选择该功能时，当前搜索词和已有的少量英文内容会发送给 ChatGPT；不可用时回退到 Wikimedia。[官方登录说明](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

联网内容可能出错，请核对可点击来源后再划入字典。文章导入只接受公开 HTTPS 页面，不尝试绕过付费墙或需要登录的网站。

录音在本机用 Vosk 转写，不上传到 ChatGPT。首次选择中文或英文录音时，会下载约 40–42 MB 的相应离线模型。图片来自 Wikimedia Commons；只在你选择后下载到本机，词条保存图片来源、作者及许可信息。

词条、图片、可选账号元数据和语音模型位于 `%LOCALAPPDATA%\PersonalDictionary\`，不随公开代码或安装包共享。数据库是 `dictionary.sqlite3`，图片在 `images\`，语音模型在 `models\`。要备份，关闭软件后复制这个文件夹。可选的 ChatGPT 账号令牌由 Windows 凭据管理器保存，不在该文件夹中。

## 从源码运行或打包

需要 Windows 10/11 和 Python 3.10 或更新版本：

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m dictionary_app
```

也可双击 `launch.bat` 建立环境并运行。执行 `build_windows.bat` 可生成 `dist\LittleAtlas\LittleAtlas.exe`。打包需要安装 `requirements-build.txt`；批处理会自动安装。

运行测试：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

界面使用 PySide6，个人词条使用 SQLite。账号授权和网页搜索的自动测试使用模拟响应；只有主动使用可选 ChatGPT 功能时才需要账号授权。

## English summary

Little Atlas is an online personal notebook with private email accounts. Articles support headings, a clickable outline, editable titles and categories, cloud autosave, and revision checks for edits from multiple devices. Research includes cited English facts and licensed reference images; selected passages can be appended to an open note. Ordinary web research and organization use no AI model tokens. The Windows desktop dictionary remains available separately, with its data stored under the current user's local app-data folder.

## License

Application code: MIT License. Wikipedia text and Wikimedia Commons images retain their own source licenses; downloaded images are accompanied by source and attribution metadata.
