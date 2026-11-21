# PlayHub Launcher

Python / PySide6 原生 Windows x64 游戏启动器，当前源码版本 **0.2.9 Alpha**。本项目沿用主页、商店、游戏库和下载管理布局；游戏内容由官方商店清单维护，不展示虚构评分。

## 0.2.9 更新

- 游戏库未安装或启动文件不存在时，主按钮显示「点击下载」；已有有效本地启动项时显示「开始游玩」。没有下载来源时明确禁用下载，不假装已安装。
- 玩家启动器默认晴蓝主题，在「设置与网盘登录 → 外观」可切换晴蓝 / 墨青绿，立即生效并保存在本地。红点和更新警示始终保持红色。
- 游戏详情新增独立的「更新日志」和「作者的话」。后者用于作者寄语、致玩家的话，不是安装说明；由管理员维护。
- 排序/筛选改为当前控件事件结束后合并刷新，避免切换排序时在信号回调中立即销毁下拉框。增加连续切换回归。
- 独立 Studio 共用原生样式和切页动效，默认墨青绿；主题和动效偏好与玩家启动器分开保存。Studio 源码不在本仓库。

## 游戏库与详情

- 详情按游戏 ID 使用最新商店资料，包括封面、截图、介绍、下载来源、更新日志与作者寄语；不以旧收藏快照覆盖新资料。
- 保留玩家自定义名称、本地启动项、安装目录和本地版本记录。
- 启动时及每 15 分钟后台检查商店版本，也可在游戏库手动检查。
- 发现可比较的新版本后，左侧游戏库显示红点，对应卡片高亮并显示版本变化；提供「有更新」筛选。查看详情不会清除提醒。
- 仅在成功解压并登记管理员配置的唯一启动项，或玩家明确确认并登记已手动安装的版本后更新本地记录。不静默覆盖旧版或存档。
- 无网络时保留缓存并提示失败；未知版本或纯本地导入不虚报“已是最新版”。版本比较依赖管理员填写的版本字段，不扫描 EXE 内部版本。

## 下载与安全解压

- HTTPS 直链：文件清单、目录确认、全局限速、暂停，以及具备服务端验证条件的断点续传。
- BitTorrent / 磁力：先获取元数据，再勾选文件；上传默认限速，下载完成停止。支持局域网发现及手动指定做种端 `IP:BT监听端口`；显式节点只在本次内存中保存，不扫描端口。Tracker 能回应不等于做种端可连接。
- MediaFire：支持标准公开单文件分享的正常下载按钮；不执行脚本，不绕过密码、登录、验证码或付费限制，暂不支持文件夹。实际可用性取决于分享状态和网络。
- 蓝奏云支持正常提取码/官方浏览器转接；坚果云保留所选文件与目录并提供官方授权续接，真实账号全链路仍需验证。百度、夸克提供官方入口，不承诺所有分享或专用客户端资源可直接下载。
- GitHub 公开 Release 附件支持源站、短测速和 GHFast / GH-Proxy 备用线路；只有 GitHub 官方来源提供可信 SHA-256 时启用镜像。无固定速度保证，绝不向镜像发送管理员令牌或网盘会话。
- 支持 ZIP、7z、TAR、TAR.GZ/TAR.BZ2/TAR.XZ，以及单文件 GZ/BZ2/XZ。内置 7z 解压依赖，不要求用户安装 7-Zip。RAR、加密包、分卷包、APK/JAR 和安装器不自动解压。
- 已完成任务可点击「解压已下载文件」，先核对任务记录的大小和 SHA-256，再解压到新的 `installed` 子目录，无需重下。
- 解压检查路径、链接、文件类型、重复路径、体积和磁盘空间；可以取消，不自动运行程序，不猜测 EXE，不覆盖原压缩包或旧游戏。
- 删除任务默认保留文件；仅在额外确认后备份并回收该任务记录的未修改文件。

## 安装与源码运行

Windows x64、Python 3.13：

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm install --no-save playwright-core
.venv/Scripts/python.exe launch.py
```

正式测试包请**完整解压整个目录后运行 `PlayHub.exe`**，不能单独移走 EXE。网盘授权使用 Microsoft Edge；源码模式另需 Node.js。完整测试包附带相关运行组件。平台密码只交给官方页面；临时会话不持久化到磁盘。

## 本地测试与构建

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -v
node tools/test_cloud_flow.cjs
.venv/Scripts/python.exe launch.py --smoke-test --data-dir validation/state --capture-dir validation/ui
.venv/Scripts/python.exe tools/build_windows.py
```

离屏自检使用独立目录，不执行游戏；覆盖页面、动效、7z 解压、更新红点和详情。公开仓库不含 Studio，相关私有测试不会要求其源码。CI 为手动触发，不会因为推送代码自动创建发行版。

## 管理商店内容

清单位于 `catalog/catalog.json`，由管理员在线维护；更新客户端源码不应覆盖该文件或已上传封面。默认地址：

`https://raw.githubusercontent.com/jkzhangc/playhub-launcher/main/catalog/catalog.json`

`merchandising.weekly_ids` 控制本周推荐；`merchandising.hero` 设置横幅。游戏常用字段：

| 字段 | 用途 |
| --- | --- |
| `id` / `version` | 稳定游戏标识和商店版本号，用于库内关联与更新检查 |
| `sources` | 下载来源列表，每项包含 `type`、`url`、`label` |
| `cover` / `screenshots` | 封面与截图 |
| `description` / `system_requirements` | 游戏介绍与系统需求 |
| `changelog` | 更新日志纯文本，可包含多版变更和换行 |
| `author_notes` | 作者寄语、致玩家的话，纯文本 |
| `executable` | 压缩包内明确的相对 EXE 路径，不接受本机绝对路径 |
| `auto_install` | 是否在玩家同意后解压支持格式，不表示自动执行 |

独立官方 Studio 可以编辑上述字段。Studio 二进制可随经确认的发行版提供，**Studio 源码、个人令牌、DPAPI 缓存与玩家本地状态不在公开仓库中**。玩家客户端不包含管理员凭据；编辑权限由 GitHub 实际身份与仓库授权校验。

## 已知限制

Alpha 尚未代码签名；未提供可信签名的自动覆盖安装、用户投稿审核或线上评论评分。P2P 速度及可用性受做种节点与网络影响；第三方网盘/镜像没有永久可用或固定速度承诺。只下载和分发你有权使用的内容。

公开客户端代码采用 MIT 许可证。Qt / PySide6 等第三方组件保留各自许可证，见 `legal/` 和构建包内 `third-party-licenses/`；Qt 以可替换动态库形式分发。
