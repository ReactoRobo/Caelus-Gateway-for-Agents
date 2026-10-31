# Caelus Gateway for Agents

让支持 Skill 和 Python 执行的助理连接自己的 Caelus 网关。

**安装 Skill → 输入 MCP 地址 → 在网关网页输入管理员密码并授权 → 开始使用。**

管理员密码只提交到网关网页。客户端获得独立授权凭证，设备操作走
Caelus Core → 功能插件，不经过 Hermes，不把 HA Token、模型 Key 或 Tunnel Token 交给助理。

## 安装与首次连接

将本仓库作为一个名为 `caelus-home` 的 Skill 安装，保留根目录的 `SKILL.md`
和 `scripts/caelus.py`。如果助理支持从 GitHub 安装 Skill，可以告诉它：

> 请安装 https://github.com/ReactoRobo/Caelus-Gateway-for-Agents 中的 caelus-home Skill，然后连接我的 Caelus 网关。

安装能力由宿主平台决定。这个提示词不保证任意版本的 WorkBuddy、豆包或云端运行环境都能自动安装。
本版本需要 Python 3.10+、Linux/macOS/WSL、出站 HTTPS 和按用户隔离的持久私有目录。
不满足条件时应使用宿主支持的连接器或秘密存储接口，不能把凭证放进聊天。

1. 用户提供 **App Host 的 MCP 地址**，例如 `https://gateway.example.com/mcp`。
2. Skill 显示授权链接和核对码。用户核对域名和核对码，在网页输入网关管理员密码，点击授权。
3. 返回助理，告诉它“授权好了”。Skill 检查状态并读取真实工具目录。
4. 可以询问家庭状态、控制设备、保存或执行模式。先绑定设备，再使用相应功能。

上述域名只是示例。本仓库不分配域名、不创建 Tunnel，也不包含可直接访问的公共网关。
配套网关 App 现可在“设置 → 远程连接”开启临时 Cloudflare Tunnel，并从 WorkBuddy/豆包工作入口
复制包含实际地址的连接指令。使用出厂密码时先引导修改密码。临时地址会变化，重新开启后可能需重新配对。
需要配套网关版本已实现 `/mcp/pair`、`/mcp/pair/status` 和 `/mcp-authorize`。
不是把任意 MCP 地址填进去就能使用这个配对协议。

## 客户端

在 Skill 目录运行（真实地址由用户提供）：

```bash
python3 scripts/caelus.py begin https://gateway.example.com/mcp --label WorkBuddy
# 在浏览器完成授权后：
python3 scripts/caelus.py status
python3 scripts/caelus.py tools
```

`call <tool-name> --request-id <UUID>` 从标准输入读取 JSON 参数。
调用格式和操作规则见 [SKILL.md](SKILL.md)，参数以网关返回的工具 schema 为准。
控制超时不自动重发；相同 UUID、工具和参数可查询原回执，不能当作新操作重复执行。

客户端使用标准库，不安装第三方依赖。它采用 MCP JSON-RPC 的 HTTP JSON 响应模式，
配对是 Caelus 自有的浏览器授权流程，**不是 OAuth**。它不提供通用 stdio MCP 代理，
也不代表 WorkBuddy 的原生 MCP 配置页会自动识别该配对流程。

## 权限与凭证

- 每个客户端生成自己的随机凭证，网关仅保存哈希。授权前无法读取工具或调用设备。
- 本版本范围是已添加的设备和本机主人的模式，不开放聊天、记忆、账号管理或密钥。
- 网关授权页可撤销单个客户端；改管理员密码、恢复出厂设置或 30 天到期后授权失效。
- 客户端凭证在 `$XDG_STATE_HOME/caelus-agent/connection.json`，默认
  `~/.local/state/caelus-agent/connection.json`；目录 0700，文件 0600。
  **不要查看、输出或提交此文件。** 这不是加密保险库，同一系统用户运行的程序仍可能读取。
- 云端 WorkBuddy 的实际隔离、持久化和密钥保护必须在对应运行环境验证；本项目不作未验证的保证。
- 远程连接要求可信 HTTPS，不忽略证书错误；本机回环测试可使用 HTTP。
- 在 `/mcp-authorize` 撤销后再执行 `python3 scripts/caelus.py forget`。
  `forget` 只删除本机文件，不能代替服务端撤销。

## Tunnel 对接

配套 Caelus 网关提供可选的专用来源服务：

```text
现有 App Host 启动参数追加：
--mcp-public-origin https://gateway.example.com --mcp-port 18895

Tunnel 公网 hostname：gateway.example.com
Tunnel 回源 service：http://127.0.0.1:18895
回源 Host：gateway.example.com
```

该端口只监听本机，公网 HTTPS 由 Tunnel 终止；仅允许授权页面、登录和 MCP 路由，
不开放完整后台、注册和设置。先更改出厂管理员密码。不要把原始 Core MCP 端口暴露到公网。
Tunnel 凭证保留在网关，和 Skill 的授权凭证分开。

## 验证范围

客户端检查：`python3 -m unittest discover -s tests -v`。
网关项目另有隔离测试，覆盖浏览器授权、CSRF、工具访问、撤销、改密码失效、
恢复状态阻断、重复控制去重和模式保存/执行；手机 320/390px 授权页面已检查。
设备操作测试使用隔离 fixture，没有控制真实家庭设备。

已使用真实 Cloudflare Quick Tunnel 对隔离网关验证公网 HTTPS、未授权拦截、配对、工具目录和撤销，
测试结束后关闭通道；没有执行家庭设备控制。仍未完成真实 WorkBuddy/豆包宿主安装和云端凭证持久化验收。
豆包工作当前是兼容环境下的测试接入，不是已上架的官方连接器。
