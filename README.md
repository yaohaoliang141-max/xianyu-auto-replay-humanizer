# xianyu-auto-replay-humanizer

闲鱼装饰画店铺的 AI 自动回复系统（线上运行版本）。在开源项目
[zhinianboke/xianyu-auto-reply](https://github.com/zhinianboke/xianyu-auto-reply)（commit `990f701`）基础上修改，
重点是让 AI 回复更像真人卖家、按商品简介和订单状态回答、减少差评和风控风险。

> 本仓库沿用原项目的 **GNU AGPL-3.0** 许可证（见 [LICENSE](LICENSE)）。原项目作者声明仅供学习研究，使用前请自行阅读原项目许可证与声明。

## 目录

| 路径 | 内容 |
|---|---|
| `app/` | 完整源代码。`common` / `backend-web` / `websocket` / `scheduler` 取自线上正在运行的镜像，和线上一致 |
| `scripts/` | 部署文件：`compose.yaml`、`Dockerfile`、`cloud_entry.py`、`cloud_health.py` |
| `prompts/ai-reply-prompt.txt` | 当前线上使用的 AI 回复提示词（三类意图共用同一份） |
| `ops/daily-check.sh` | 每日只读风控/健康检查脚本 |
| `ops/publish.ps1`、`ops/export-from-server.sh` | 从服务器导出当前线上代码（自动做密钥扫描，发现密钥就拒绝）并同步到本仓库 |
| `infra.env.example`、`runtime-settings.example.json` | 配置模板（只有字段，没有任何密码） |
| `CHANGES.md` | 每次改动记录 |

## 不在仓库里的东西（敏感，永远不要提交）

`infra.env`（数据库/Redis 密码）、`runtime-settings.json`、`data/`（闲鱼登录 Cookie、浏览器数据、日志、备份）、
数据库导出、`migration/` 变更备份。AI 接口密钥和闲鱼账号信息保存在服务器 MySQL 里，也不在仓库中。

## 部署

目录结构与服务器 `/opt/xianyu-local-modified` 一致：

```bash
git clone https://github.com/yaohaoliang141-max/xianyu-auto-replay-humanizer.git /opt/xianyu-local-modified
cd /opt/xianyu-local-modified
cp infra.env.example infra.env                      # 填入密码
cp runtime-settings.example.json runtime-settings.json
docker build -f scripts/Dockerfile -t xianyu-local:repo .
# 把 scripts/compose.yaml 里各服务的 image 改成 xianyu-local:repo
cd scripts && docker compose -p xianyu-ecs -f compose.yaml --env-file ../infra.env --profile live up -d
```

启动后在后台页面扫码登录闲鱼账号，在 AI 设置里填写模型接口（目前用阿里云百炼 `qwen3.7-flash`，OpenAI 兼容接口），
并把 `prompts/ai-reply-prompt.txt` 填到 价格 / 技术 / 默认 三类提示词里。

## 主要改动（详见 CHANGES.md）

- 提示词重写：自然亲切的卖家口吻；所有规则按买家意思理解，不是关键词匹配；不知道的事说「我问下店主」，不编造。
- 手绘按商品标题/简介判断（写了「手绘」就是手绘，「非手绘」除外），其他商品统一说「高清艺术微喷工艺」；自动去掉「纯手绘」「一笔笔」「打印」等用词。
- 记录闲鱼「订单已签收」卡片，AI 能看到订单状态；签收后买家表达任何不满意，统一引导运费险退货。
- 每个会话 AI 最多回复 7 次；回复随机延迟 7~20 秒；自动评价逐条排队、间隔 10~20 秒；关闭自动求小红花。
