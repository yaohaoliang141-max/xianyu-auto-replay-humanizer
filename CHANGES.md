# 改动记录

## 2026-11-27 — 24h watchdog on the server, alerts straight to Feishu

- New `ops/watchdog.py`, installed at `/opt/xianyu-local-modified/watchdog/` with `/etc/cron.d/xianyu-watchdog` (every 5 min). It runs on the server, so alerts still arrive when the owner's PC is off. Read-only.
- Checks: services healthy; Xianyu IM connected (must fail twice in a row); token 余额不足 / expired token in use / renew failed; AI API errors; failed signed-for greetings; slider or account validation; risk words (违规/处罚/封禁/限制登录…); order sync last success > 60 min; no buyer message for 6h (08–23 Beijing); memory < 200 MB, disk ≥ 90%.
- Each problem is sent once and repeated at most every 2h. Ongoing problems get a 「已恢复」 message when they clear. The first run after 09:00 adds a daily "monitor alive" line. A failed Feishu send rescans the same window next run.
- The webhook lives only on the server (`watchdog/feishu-webhook`, chmod 600) and is not in this repo. Remove: `rm /etc/cron.d/xianyu-watchdog`.
- The first scan found a real 「内容违规处罚」 notice from Xianyu on 2026-11-26 08:31.

## 2026-11-26 — Signed-for greeting: two short messages, and make sure it is sent

- Code (`xianyu_async.py`, image `greet-two-ws-20261126`): the greeting is now two messages, 「亲，画已经签收啦，希望您喜欢😊」 then 「不满意可以直接退货，有运费险的～」, 2–4s apart.
- Reliability: if the order isn't synced yet, look again every minute for up to 15 min. If sending fails, retry 3 times 30s apart, continuing from the message that failed. If all fail, remove the sent mark so a repeated 签收 notice re-sends it. Still once per order (Xianyu sometimes pushes the notice twice). Refunding orders now get it too; refunded and cancelled orders don't.
- `ops/daily-check.sh`: `signed_greeting_sent / signed_greeting_failed`; failures are flagged yellow so the owner can message those buyers by hand.
- Rollback: `migration/greet-two-20261126/restore.sh`.

## 2026-11-26 — Cleanup: remove conflicting and duplicate rules

- Code (`ai_reply_engine.py`, image `cleanup-ws-20261126`): the upstream 「议价设置：最大优惠10%/100元」 block is no longer sent to the AI (it contradicted 「标价就是卖价」). The order lookup now returns an explicit stage (`none/pending/shipped/signed/refunding/refunded/cancelled`) instead of searching the status text for 「售后阶段/已发货阶段」. An unused constant was removed.
- Prompt (4218 → 3806 chars): removed the dead refund-card rule; merged the after-shipping complaint rule into one line (output `[不满意]`, the program sends the script); fixed 「不确定就说需要确认」 and 「不要主动提退货」 contradictions; shortened the 假一赔十 and 「赔/保证」 rules.
- Kept on purpose: the per-status shipping lines. Without them the AI made up a reason (「颜料需要晾干一天」) when asked when an order ships.
- Rollback: `migration/cleanup-20261126/restore.sh`.

## 2026-11-26 — Daily check: order sync health; fix log ordering

- `ops/daily-check.sh` now reports `order_sync_runs / order_sync_fail / order_sync_ok_last / newest_order`. If order sync stops, the AI can't recognise buyers who bought, so the risk check flags it red after 1 hour.
- Fixed: "last" times read across two log files came out in the wrong order (needed `sort`). Token failures now also show `token_renew_fail_last`, so old, already-fixed failures don't raise a red alarm.

## 2026-11-26 — Second complaint check for buyers whose order has shipped

- Code (`ai_reply_engine.py`, image `complaint-check-ws-20261126`): for shipped / signed / refunding buyers, each message is first classified by a separate AI call as 满意 / 中性 / 不满意. 不满意 → apology + return script straight away; otherwise the normal reply runs (its own `[不满意]` tag still triggers the return script). If the check fails, the normal reply runs.
- Tested on 13 tricky messages (praise, neutral questions, sarcasm, subtle complaints, emoji): 13/13 after wording fixes.
- Rollback: `migration/complaint-check-20261126/restore.sh`.

## 2026-11-26 — Recognise buyers who already bought, even when the order isn't linked to the chat

- Found: many orders have no chat_id (27 of 33 completed, 35 of 116 shipped), so buyers who had the goods were treated as strangers: abuse → no reply, 4-reply cap, no return script.
- Code (`ai_reply_engine.py`, image `received-ws-20261126`): order lookup is chat → buyer + item → chat-log shipping messages → buyer's other orders (not cancelled). A `signed_at` record means received regardless of a stale status. The 4-reply cap also checks the buyer's own orders. Refunded buyers who still complain get an apology only, no arguing.
- Checked on 167 real chats from the last 14 days: 12 chats now get a more accurate status; strangers still count as no order.
- Rollback: `migration/received-detect-20261126/restore.sh`.

## 2026-11-25 — Buyers who ask 假一赔十 get no reply before shipping

- Prompt + code (`ai_reply_engine.py`, image `fake10-ws-20261125`): before shipping (no order, unpaid, paid-not-shipped), a buyer asking 假一赔十/假一赔N gets no reply; the AI outputs `NO_REPLY 假一赔十` and the program saves a marker in the chat, so every later message from that buyer is also ignored. Refund/return cards still get their fixed reply. After shipping it counts as dissatisfaction → apology + return script. 「保真吗」 alone is still answered by craft.
- Shipped stage: if a reply is blocked by the money-promise guard, the return script is sent instead of a vague line.
- Rollback: `migration/prompt-noreply-fake10-20261125/restore.sh`.

## 2026-11-25 — Prompt: sarcasm counts as a complaint; answer 假一赔十 by what the item is

- Sarcastic praise after shipping (「呵呵 真是好画啊」) now counts as dissatisfaction → return script.
- 「假一赔十吗」「保真吗」 are answered by how the painting is made (hand-painted / micro-spray), never with a vague 「以平台规则为准」; still no promise of compensation.
- Prompt only. Rollback: `migration/prompt-edge-20261125/restore.sh`.

## 2026-11-25 — Once shipped, any complaint gets only the return script

- Cause: a buyer had two orders in one chat (an unpaid duplicate that was cancelled, and the real shipped one). The AI read the newer cancelled order, thought nothing was bought, and kept arguing 「是手绘的」.
- Code (`ai_reply_engine.py`, image `shipped-return-ws-20261125`): with several orders in one chat, the real one wins (refunding > shipped/completed > pending_ship > refunded > cancelled). If no order matches, 「你已发货 / 订单已签收 / 确认收货」 system messages in the chat log count as shipped/signed. Shipped (in transit) and refunding now carry the same rule as signed: any dissatisfaction → `[不满意]` → apology + return script; no talk of 手绘/工艺.
- Prompt: the after-sale rule covers 已发货 / 已签收 / 已确认收货 / 退款中; no more "explain hand-painted, then the return line".
- Rollback: `migration/shipped-return-20261125/restore.sh`.

## 2026-11-25 — Greeting when an order is signed for; listing descriptions

- Code (`xianyu_async.py`, image `signed-greet-ws-20261125`): when Xianyu's 「订单已签收」 workbench card arrives, the buyer gets one fixed message 5–15s later (signed-for greeting, mentions 7-day no-reason returns and return-shipping insurance). Once per order (`metadata.signed_greeting_sent`); skipped for refunding/refunded/cancelled orders. Rollback: `migration/signed-greeting-20261125/restore.sh`.
- Listings (data only, no code): 50 of 60 paintings got the return note in their description and lost 「不退不换」-type wording, 「假一赔十」 and 「其他尺寸也有」 (seller backend edit API, description only; location and condition verified unchanged). 10 can only be edited in the Xianyu app.

## 2026-11-25 — Size: more description formats; unknown size → point to the description

- Code (`ai_reply_engine.py`, image `size-desc-ws-20261125`): the size finder also reads `30cm 30cm`, `30cm40cm`, `3030cm` (lost ×) and a single side like `尺寸：约30cm`.
- Data: the 42 items that had no description in the catalog were filled from the seller backend (read-only edit-detail API); 46 of 68 items now have a size the program can find.
- Prompt: when neither title nor description has a size, reply 「尺寸就是简介里写的哦～」; never say it needs checking or ask the owner.
- Rollback: `migration/size-desc-20261125/restore.sh`.

## 2026-11-25 — Size: read it from title + whole description; only one size exists

- Code (`ai_reply_engine.py`, image `size-line-ws-20261125`): the size is extracted from the title and the full description (30*40, 30x40, 30×40, 30✖️40, 30乘40, with or without cm) and passed to the AI as its own line `商品尺寸: …`. The AI only says it needs to check when neither the title nor the description has a size.
- Prompt: all paintings come in one size only. Asking for a bigger/smaller/custom size → 「目前只有这一个尺寸哦～」, no more 「其他尺寸我问下店主哦」.
- Rollback: `migration/size-one-20261125/restore.sh`.

## 2026-11-25 — Alert when the login-token service runs out of balance

The scheduler's token renewal task renews the Xianyu IM token through a paid remote API. When that balance ran out (11-24 05:55), renewal failed silently; the websocket kept an expired token and stopped receiving buyer messages after its next reconnect (11-25 07:11). `ops/daily-check.sh` now reports `expired_token_in_use`, `token_balance_fail`, `token_renew_fail` and `last_buyer_msg`, and the daily risk check flags any of them in red. A websocket-side renewal fix was built and tested but not deployed (the scheduler already renews).

基础：zhinianboke/xianyu-auto-reply `990f701`，2026-11-16 迁移到阿里云 ECS（Docker Compose，六个服务）。
11-16 ~ 11-19 期间已有的定制（付款确认、一口价、发货提醒、随机延迟等）已包含在 `app/` 中。

## 2026-11-24

- **买家申请退货/退款时固定回复**（`ai_reply_engine.py`，不调用 AI）：
  - 发起退货退款 →「收到啦～我这边现在在忙，12小时内会同意退货的，不好意思哈🙏」
  - 发起退款 / 修改退款申请 →「收到啦～我这边现在在忙，12小时内会处理的，不好意思哈🙏」
  - 这几条固定回复不受每个会话 7 次回复上限限制（`ai_reply_engine.py` 和 `auto_reply_service.py` 两处上限检查都放行）。
  - 订单「退款中」时，AI 按同样意思回答，不再谈商品性质。
- **没下单的人一上来就骂或贬低，不回复**（`ai_reply_engine.py`）：由 AI 按意思判断，输出 NO_REPLY 时不发送，也不改发默认回复；正常提问（包括质疑是不是手绘）照常回答。已签收的买家不受影响。
- **回复次数上限**（`ai_reply_engine.py`）：没下单的会话最多回复 4 次；已经下单的会话不限次数（原来统一 7 次）。退货/退款申请卡片照样不受限。
- **催发货先道歉**：订单状态「待发货」「已发货」时，买家催发货、问怎么还没到 → 先诚恳道歉，再说原来的发货话术（已预约快递小哥取件 / 已经发出，订单里可以看物流）。
- **道歉分多条发**：签收后不满意 → 5 条（道歉 / 运费险退货话术 / 您现在可以申请退货退款，我12小时内会同意的 / 真的实在不好意思 / 这边非常抱歉影响您的心情了🙏）；买家申请退货/退款 → 3 条（收到啦…12小时内… / 真的实在不好意思 / 这边非常抱歉影响您的心情了🙏）。用 `######` 分隔；`auto_reply_service.py` 多条之间的间隔从 0.5 秒改为随机 2~4 秒。
- **签收后是否不满意由 AI 标记判断**：AI 判断买家不满意时只输出 `[不满意]`，程序据此发 5 条道歉；不再看回复里有没有「退货/运费险」字眼（之前平和地问「是手绘的吗」也会误发道歉）。签收后平和地问商品性质 → 只回「宝贝收到就好～挂起来很好看的😊」。
- **好评后感谢消息发不出去**（`rate_task.py`）：每晚批量评价发感谢消息时漏传买家 ID（`to_user_id`），服务端拒绝。现在补上了。

## 2026-11-23

**签收 / 确认收货后的回复**（`ai_reply_engine.py`）
- 起因：一位买家签收后质疑「不是手绘」，AI 的回复被安全过滤拦截，发出去的是「具体以商品详情和平台规则为准。」。
- 签收后不再谈手绘、微喷、工艺、材质等商品性质：不给 AI「制作方式」，回复里谈这些的句子会被去掉。
- 买家夸奖：只表示感谢。买家不满意（由 AI 按意思判断）：统一发「真的非常非常抱歉，让您不满意了，是我们没做好🙏 您好，我们有运费险，这边您可以直接退货，运费平台也会赔付给您，辛苦了～」。
- 安全过滤：放行退货话术的常见说法（运费会由平台赔付 / 运费险会赔付给您 等）。签收后回复被拦截时，改发上面的道歉加退货话术。被拦截的原文会写进日志。

## 2026-11-22

**自动评价改为每天 20:00 批量评价**
- `websocket/.../xianyu_async.py`：收到「去评价」提醒不再即时评价，留给每日批量。
- `scheduler/.../rate_task.py`：每天 20 点（北京时间，服务器时区）运行一次（同一天不重复）；评价最近 14 天已发货/已完成且未评价的订单；一条一条，固定间隔 20 秒。评价内容和好评后感谢消息不变。

**手绘判断改回按简介**：店主新增了多幅手绘，取消 3 件写死的手绘名单。
- `ai_reply_engine.py` 新增 `_made_label`：标题或简介写了「手绘」就是手绘款；「非手绘/不是手绘/不是纯手绘」等为微喷款；读不到商品资料（如新上架还没同步）时标为「不确定」，AI 回答「这个我确认一下哦」。
- 提示词增加「不确定」情况的回答。去掉「纯手绘/一笔笔」、「打印→高清艺术微喷」的过滤保持不变。

## 2026-11-21

**AI 提示词（`prompts/ai-reply-prompt.txt`）**
- 从约 3200 字的死板固定话术，改为自然亲切的卖家口吻；用历史 323 条真实买家消息回放测试后上线。
- 所有规则按买家意思理解，不是关键词；不知道的事（框材质、画面细节、库存、别的款、看不到的图片）说「这个我问下店主哦」。
- 尺寸、边框直接按当前商品简介回答；简介里的宣传话（假一赔十、价格可聊、发货前拍视频）不算承诺。
- 买家抱怨时道歉、不争辩；避免「赔」「保证」字样（会被安全过滤整条替换）。
- 所有画背面没有支架，回答「没有支架哦，是挂墙的～」，不提小钩子。
- 换款：未发货 → 申请退款后重新拍；已发货 → 不能换款。
- 签收 / 确认收货后买家表达任何不满意 → 「您好，我们有运费险，这边您可以直接退货，运费平台也会赔付给您，辛苦了～」。

**代码**
- `websocket/app/services/xianyu/ai_reply_engine.py`
  - 每个会话 AI 回复上限 5 → 7。
  - `HANDMADE_ITEM_IDS` 手绘白名单（鸢尾花、盛开的杏花、莫奈·塞纳河晨光），向 AI 提供「制作方式」。
  - `_soften_handmade_words`：去掉「纯手绘」「一笔笔」，「打印/印刷」改为「高清艺术微喷」。
  - `_lookup_order_status`：向 AI 提供「订单状态」（待发货 / 运输中 / 已签收 / 已确认收货 / 退款中…）。
  - 安全过滤放行店主确认的退货话术「运费平台也会赔付给您」。
- `websocket/app/services/xianyu/message_handler.py`：收到「订单已签收」卡片时，把 `signed_at` 记到对应订单。
- `websocket/app/services/xianyu/auto_reply_service.py`：回复延迟改为 最小值 + 0~13 秒（账号设置最小值 7 → 7~20 秒）。
- `websocket/app/services/xianyu/xianyu_async.py`：即时自动评价改为后台排队，逐条间隔 10~20 秒。
- `scheduler/app/services/scheduler/rate_task.py`：定时补评价间隔 2 秒 → 10~20 秒。

**设置（数据库，不在仓库）**：`reply_delay_seconds=7`，`auto_red_flower=0`，商品特殊说明统一为全国包邮。

**价格不报数字（晚间追加）**：店里常有平台活动，标价不一定是实付价。
- `ai_reply_engine.py` 不再把标价传给 AI（改为「以买家下单页面显示为准」）；回复里出现「XX元/块/¥」时整条换成「宝贝，标价就是卖价哈，没有少哦～😊」。
- 提示词：所有问价、砍价、问总价，统一和蔼地回答「标价就是卖价，没有少哦～」，不报数字、不算总价。

**运维**：新增 `ops/daily-check.sh` 每日只读检查；服务器 `vm.swappiness` 运行时调为 10（重启后恢复）。
