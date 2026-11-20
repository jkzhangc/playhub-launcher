# PlayHub Launcher

Python / PySide6 原生 Windows 游戏启动器，当前版本 **0.2.0 Alpha**。

## 测试版范围

- 空商店起步，游戏由官方另行添加；不内置 L3DRE 或示例评分。
- 商店横幅、分类排序、游戏详情、游戏库与下载管理沿用确认的界面结构。
- 官方商店清单支持游戏资料、封面截图、本周推荐顺序与横幅文案。
- HTTPS 下载支持目录选择、全局限速、暂停与有验证条件的断点续传。
- BitTorrent / 磁力支持先取元数据、再勾选文件；默认限制上传，完成即停止。
- 蓝奏云提供正常提取码和浏览器授权转接。坚果云保留所选文件/目录并提供官方登录续接；登录后完整链路仍需实际账号验证。
- 百度、夸克提供官方入口，不承诺所有分享、会员资源或专用客户端资源均可直接下载。
- 下载任务删除默认保留文件；单独确认后，仅备份并回收本任务记录的未修改文件。
- ZIP 可按管理员明确配置的相对 EXE 启动项安全解压、登记，不自动运行。APK 不是 Windows 游戏。
- GitHub Release 附件支持源站、短测速和可选第三方镜像回退；无可信参考 SHA-256 不启用镜像。

**尚未上线：** 在线评论评分、用户投稿审核服务、可信签名自动安装更新。当前只查询/下载版本，不静默覆盖程序。

## 运行源码

Windows x64、Python 3.13：

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm install --no-save playwright-core
.venv/Scripts/python.exe launch.py
```

网盘授权组件需要 Microsoft Edge 和 Node.js。完整测试 ZIP 随附 Node.js 和 Playwright 运行组件；源码模式使用本机安装的组件。官方登录密码不交给 PlayHub；会话仅保存在内存，不持久化令牌或 Cookie。

## 本地测试

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -v
node tools/test_cloud_flow.cjs
.venv/Scripts/python.exe launch.py --smoke-test --data-dir validation/state --capture-dir validation/ui
```

`--smoke-test` 使用离屏渲染，不修改用户日常档案。测试不运行游戏或下载第三方可执行文件。

## 管理商店

公开清单：`catalog/catalog.json`。默认客户端地址：

`https://raw.githubusercontent.com/jkzhangc/playhub-launcher/main/catalog/catalog.json`

`merchandising.weekly_ids` 控制本周推荐顺序；`merchandising.hero` 设置横幅。每款游戏可填写 `sources`、`cover`、`screenshots`、`system_requirements`、`executable` 和 `auto_install`。

独立官方管理工具不在本公开仓库和公开 Release 中。它以 GitHub 真实身份和官方仓库权限控制编辑，只有作者可邀请管理员；不向客户端分发管理员凭据。

## 分发与安全

测试包需要**解压整个目录后运行 `PlayHub.exe`**，不能单独取走 EXE。Alpha 尚未代码签名；校验文件与发布说明应由用户核对。镜像是第三方传输，不是可信身份来源。仅下载与分发你有权使用的内容。

公开客户端代码采用 MIT 许可证。Qt / PySide6 等第三方组件保留各自许可证，见 `legal/`。Qt 为可替换动态库形式分发；相关源代码见 https://code.qt.io/qt/ 和 https://code.qt.io/pyside/pyside-setup/ 。
