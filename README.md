# Little Atlas · 个人字典

Little Atlas 是一款 Windows 本地桌面软件。输入今天学到的中文或英文主题，查看有来源的英文补充资料，再用笔划出你真正想留下的内容。词条按章节编成自己的字典。每个人第一次打开时都是空白的，个人数据留在自己的电脑上。

## 使用

1. 解压完整的 `LittleAtlas-Windows.zip`，双击 `LittleAtlas.exe`。不要单独移走 EXE；它需要旁边的 `_internal` 文件夹。
2. 在中央输入卡片中输入中文或英文，按 Enter 或点击搜索键。Shift + Enter 换行。首次使用时可在浏览器中授权自己的 ChatGPT 账号；未连接时仍可使用 Wikimedia 的公开资料。
3. 搜索结果标题旁有三支笔：**选择笔**拖过的英文才会进入字典；**黄色荧光笔**和**红笔**用来标注重点，不会单独添加内容。按 Ctrl + Z 撤销上一笔。核对资料来源、章节和图片后，点击输入卡片里的 **＋** 保存。没有搜索结果时，＋可手动新建英文词条。
4. 麦克风可选择中文或 English 录音。再次点击后转成可编辑文字，检查无误再搜索。右上角目录键打开已收藏词条；正文可继续编辑、标注和自动保存。

首页采用单一的简洁界面，没有每日画风、装饰背景或空白词条例子。菜单只显示目录。右键点击搜索键可连接、更换或退出 ChatGPT 账号。

## 联网研究与隐私

Little Atlas 使用 [Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart) 让符合资格的用户以自己的 ChatGPT 账号授权；软件不会读取 Codex Desktop 的登录文件，也不包含共享 API 密钥。登录令牌保存在当前 Windows 用户的凭据管理器中。首次授权会打开系统浏览器，之后返回桌面软件。[官方登录说明](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

连接后，当前搜索词和已有的少量英文内容会发送给 ChatGPT，用于避免重复并通过联网搜索找资料。软件只展示带可点击来源的英文建议；账号或网页搜索不可用时，回退到 Wikipedia、Wikidata 和 Wikimedia Commons。联网内容可能出错，请核对来源后再划入字典。网页搜索功能取决于账号和模型的可用权限。[官方联网搜索说明](https://developers.openai.com/api/docs/guides/tools-web-search)、[账号功能限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)

录音在本机用 Vosk 转写，不上传到 ChatGPT。首次选择中文或英文录音时，会下载约 40–42 MB 的相应离线模型。图片来自 Wikimedia Commons；只在你选择后下载到本机，词条保存图片来源、作者及许可信息。

词条、图片、账号元数据和语音模型位于 `%LOCALAPPDATA%\PersonalDictionary\`，不随公开代码或安装包共享。数据库是 `dictionary.sqlite3`，图片在 `images\`，语音模型在 `models\`。要备份，关闭软件后复制这个文件夹。个人账号令牌由 Windows 凭据管理器保存，不在该文件夹中。

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

界面使用 PySide6，个人词条使用 SQLite。账号授权和网页搜索的自动测试使用模拟响应；真实 ChatGPT 登录需要每位用户在首次使用时自行授权。

## English summary

Little Atlas is a local Windows personal dictionary. Search a topic in Chinese or English, review cited English facts, paint exact phrases into your own entry, annotate them, and organize entries by chapter. Each install starts empty. ChatGPT sign-in is optional for broader web research; Wikimedia remains available as a fallback. Personal data is stored under the current user's local app-data folder.

## License

Application code: MIT License. Wikipedia text and Wikimedia Commons images retain their own source licenses; downloaded images are accompanied by source and attribution metadata.
