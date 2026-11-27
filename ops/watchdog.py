#!/usr/bin/env python3
"""24h watchdog for the Xianyu auto-reply server. Runs on the server itself (cron, every 5 minutes),
so it keeps working when the owner's PC is off. Read-only: it changes nothing in the app.

Problems go straight to the owner's Feishu group bot. Each problem is sent once, repeated at most every
2 hours while it lasts, and a 「已恢复」 message is sent when it clears. The first run after 09:00 each day
adds a short "watchdog alive" message (no message that day = the watchdog itself stopped). `--test` sends
one test message.
Also (2026-11-27, owner's request): every new refund request / finished refund, and every time the AI sent the
「让您不满意了…可以直接退货」 script to a buyer who already paid, is sent with item, amount, order stage and the
buyer's own words (no nickname, receiver, address or phone)."""
"""

Files (server, not in git):
  /opt/xianyu-local-modified/watchdog/feishu-webhook   webhook URL, chmod 600 — never print or commit it
  /opt/xianyu-local-modified/watchdog/state.json       which problems are open, last check time
Never puts buyer names, addresses, phones or chat text into a message."""
import json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta

BASE = "/opt/xianyu-local-modified"
HERE = BASE + "/watchdog"
STATE = HERE + "/state.json"
WS_LOG = BASE + "/data/logs/websocket/websocket.log"
SCHED_DIR = BASE + "/data/logs/scheduler"
REPEAT_S = 2 * 3600
ORDER_SYNC_MAX_MIN = 60
QUIET_MAX_H = 6


def sh(cmd, timeout=60):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def sql(q):
    q = q.replace('"', '\\"')
    return sh("docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p\"$MYSQL_ROOT_PASSWORD\" --default-character-set=utf8mb4 "
              f"xianyu_data -N -e \"{q}\" 2>/dev/null'").strip()


def send(text):
    url = open(HERE + "/feishu-webhook", encoding="utf-8").read().strip()
    assert url.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/"), "bad webhook"
    text = re.sub(r"1[3-9]\d{9}", "[手机号已隐藏]", "【闲鱼监控】" + text)[:3000]
    req = urllib.request.Request(url, json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    return resp.get("code", resp.get("StatusCode")) == 0


def log_lines(path_list, since):
    """Lines (sorted) from the given log files with a timestamp >= since ('YYYY-mm-dd HH:MM:SS')."""
    out = []
    for p in path_list:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    if ln[:19] >= since:
                        out.append(ln.rstrip("\n"))
        except OSError:
            pass
    return sorted(out)


def sched_files():
    try:
        fs = [os.path.join(SCHED_DIR, f) for f in os.listdir(SCHED_DIR) if f.startswith("scheduler")]
        return sorted(fs, key=os.path.getmtime)[-2:]
    except OSError:
        return []


def im_status():
    code = r'''
import os, json, httpx, pymysql
from urllib.parse import quote
db = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]), user=os.environ["MYSQL_USER"],
                     password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DATABASE"], charset="utf8mb4")
c = db.cursor()
c.execute("SELECT account_id FROM xy_accounts WHERE id=1"); a = c.fetchone()[0]
c.execute("SELECT value FROM xy_system_settings WHERE `key`='security.internal_api_token'"); t = c.fetchone()[0]
r = httpx.get("http://127.0.0.1:8090/internal/accounts/" + quote(str(a), safe="") + "/status",
              headers={"X-Internal-Token": t}, timeout=10, trust_env=False)
d = (r.json() or {}).get("data") or {}
print(json.dumps({k: d.get(k) for k in ("running", "is_connected", "connection_state")}))
'''
    try:
        out = subprocess.run(["docker", "exec", "-i", "xianyu-ecs-websocket-1", "python", "-"], input=code,
                             capture_output=True, text=True, timeout=40).stdout
    except Exception:
        out = ""
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        return {}


def db(query, params=None):
    """Run one SELECT inside the websocket container (it has the DB driver and credentials); rows as lists."""
    code = r'''
import os, sys, json, pymysql
a = json.loads(sys.stdin.readline())
db = pymysql.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ["MYSQL_PORT"]), user=os.environ["MYSQL_USER"],
                     password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DATABASE"], charset="utf8mb4")
c = db.cursor(); c.execute(a["q"], a["p"])
print(json.dumps([list(r) for r in c.fetchall()], default=str, ensure_ascii=False))
'''
    out = subprocess.run(["docker", "exec", "-i", "xianyu-ecs-websocket-1", "python", "-c", code],
                         input=json.dumps({"q": query, "p": params or []}) + "\n",
                         capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError("db query failed")
    return json.loads(out.stdout.strip().splitlines()[-1])


def clip(s, n=60):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def buyer_words(chat_id, buyer_id, upto=None, n=3):
    """Buyer's last few messages in this chat (text only, no names)."""
    rows = db("SELECT source_message FROM xy_auto_reply_message_logs WHERE (chat_id=%s OR sender_user_id=%s) "
              "AND decision_reason NOT IN ('self_message','system_message') AND source_message IS NOT NULL "
              + ("AND id < %s " if upto else "") + "ORDER BY id DESC LIMIT %s",
              [chat_id or "-", buyer_id or "-"] + ([upto] if upto else []) + [n])
    words = [clip(r[0], 50) for r in rows if r[0] and not str(r[0]).startswith("[")]
    return "；".join(f"「{w}」" for w in reversed(words)) or "（没说话）"


STAGE = {"pending_ship": "已付款待发货", "shipped": "已发货", "completed": "已确认收货",
         "refunding": "退款中", "refunded": "已退款", "cancelled": "已关闭"}


def order_events(st):
    """New refund requests, finished refunds, and complaints from paid buyers -> list of messages.
    The first run only remembers what is there now (no backlog)."""
    msgs = []
    rows = db("SELECT o.order_no, o.status, o.amount, o.placed_at, o.chat_id, o.buyer_id, "
              "JSON_EXTRACT(o.metadata,'$.signed_at') IS NOT NULL, "
              "(SELECT title FROM xy_catalog_items c WHERE c.item_id=o.item_id LIMIT 1) "
              "FROM xy_orders o WHERE o.status IN ('refunding','refunded')")
    seen = st.get("refund_seen")
    cur = {r[0]: r[1] for r in rows}
    if seen is not None:
        for no, status, amount, placed, chat, buyer, signed, title in rows:
            if seen.get(no) == status:
                continue
            if status == "refunding" or (status == "refunded" and no not in seen):
                head = "💸 有人申请退款" if status == "refunding" else "💸 有一单退款了（没经过「退款中」就直接退了）"
                msgs.append(f"{head}\n商品：{clip(title, 40) or '（未知商品）'}\n金额：¥{amount}　下单：{str(placed)[5:16]}"
                            f"　{'已签收' if signed else '未签收'}\n买家最近说的话：{buyer_words(chat, buyer)}")
            elif status == "refunded":
                msgs.append(f"✔️ 已退款：{clip(title, 30) or '（未知商品）'}　¥{amount}")
    st["refund_seen"] = cur

    last = st.get("complaint_last_id")
    if last is None:
        st["complaint_last_id"] = (db("SELECT COALESCE(MAX(id),0) FROM xy_auto_reply_message_logs") or [[0]])[0][0]
        return msgs
    rows = db("SELECT l.id, l.chat_id, l.sender_user_id, l.item_title, l.source_message, l.created_at, "
              "(SELECT o.status FROM xy_orders o WHERE (o.chat_id=l.chat_id OR o.buyer_id=l.sender_user_id) "
              "AND o.status<>'cancelled' ORDER BY o.id DESC LIMIT 1), "
              "(SELECT JSON_EXTRACT(o.metadata,'$.signed_at') IS NOT NULL FROM xy_orders o WHERE "
              "(o.chat_id=l.chat_id OR o.buyer_id=l.sender_user_id) AND o.status<>'cancelled' ORDER BY o.id DESC LIMIT 1) "
              "FROM xy_auto_reply_message_logs l WHERE l.id > %s AND l.reply_text LIKE %s ORDER BY l.id",
              [last, "%让您不满意了%"])
    for lid, chat, buyer, title, src, at, status, signed in rows:
        stage = "已签收" if signed and status in ("shipped", "pending_ship") else STAGE.get(status, "查不到订单")
        msgs.append(f"😟 有买家不满意（AI 已引导退货）\n商品：{clip(title, 40) or '（未知商品）'}　订单：{stage}　{str(at)[5:16]}\n"
                    f"买家说：「{clip(src, 80)}」\n前面几句：{buyer_words(chat, buyer, upto=lid, n=4)}")
        st["complaint_last_id"] = lid
    return msgs


def checks(since):
    """Return {key: problem text} for every problem seen now."""
    p = {}
    now = datetime.now()

    # 1) containers
    bad = [ln for ln in sh("docker ps -a --filter name=xianyu-ecs --format '{{.Names}} {{.Status}}'").splitlines()
           if ln and ("healthy" not in ln or "unhealthy" in ln) and not ln.split()[0].endswith("-init")]
    if bad:
        p["containers"] = "有服务不正常：" + "；".join(bad)

    # 2) connection to Xianyu IM (counts only if it is down on two checks in a row, i.e. ~10 minutes)
    try:
        st = im_status()
    except Exception:
        st = {}
    if not (st.get("running") and st.get("is_connected") and st.get("connection_state") == "connected"):
        p["im_down"] = f"和闲鱼的消息连接断开了（状态：{st.get('connection_state') or '查不到'}），买家消息现在没人回。"

    # 3) websocket log since the last check
    ws = log_lines([WS_LOG], since)
    sc = log_lines(sched_files(), since)
    def hit(lines, pat):
        r = re.compile(pat)
        return [ln for ln in lines if r.search(ln)]
    if hit(ws + sc, "余额不足"):
        p["token_balance"] = "取登录 token 的接口提示「余额不足」，需要你去充值，不然 token 过期后就收不到消息。"
    if hit(ws, "暂时使用已过期Token缓存"):
        p["token_expired"] = "正在用已过期的登录 token，续期没成功，随时可能断线。"
    if hit(sc, "续期未成功"):
        p["token_renew"] = "登录 token 续期失败（定时任务）。"
    if hit(ws, r"AccessDenied|PermissionDenied|ai_reply_engine.*(API调用失败|Error code)"):
        p["ai_api"] = "AI 接口报错（可能是阿里云 AI 额度用完或没权限），AI 现在回不了消息。"
    g = hit(ws, r"签收问候：订单.*(重试3次都没发出去|等了15分钟)")
    if g:
        p["greeting"] = f"有 {len(g)} 个订单的签收问候没发出去，请到闲鱼手动给买家发一下。"
    if hit(ws, r"检测到需要滑块验证|FAIL_SYS_USER_VALIDATE"):
        p["slider"] = "闲鱼要求滑块验证 / 账号验证，可能需要你在手机上处理一下。"
    risk = hit(ws, r"违规|处罚|封禁|账号异常|限制登录|风险账号")
    if risk:
        words = sorted(set(m for ln in risk for m in re.findall(r"违规|处罚|封禁|账号异常|限制登录|风险账号", ln)))
        p["risk"] = "日志里出现账号风险字眼：" + "、".join(words) + "。请打开闲鱼看一下有没有通知。"

    # 4) order sync: last successful run
    day = log_lines(sched_files(), (now - timedelta(hours=24)).strftime("%F %T"))
    ok = [ln for ln in day if "【定时获取闲鱼订单】执行完成" in ln and "成功1/" in ln]
    last_ok = ok[-1][:19] if ok else ""
    if not last_ok or datetime.strptime(last_ok, "%Y-%m-%d %H:%M:%S") < now - timedelta(minutes=ORDER_SYNC_MAX_MIN):
        p["order_sync"] = (f"订单同步超过 {ORDER_SYNC_MAX_MIN} 分钟没成功了（上次成功：{last_ok[5:16] or '24小时内没有'}）。"
                           "AI 可能认不出买过东西的买家。")

    # 5) no buyer messages for a long time (daytime only)
    if 8 <= now.hour < 23:
        last = sql("select max(source_message_time) from xy_auto_reply_message_logs "
                   "where decision_reason not in ('self_message','system_message')")
        try:
            lt = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
            if lt < now - timedelta(hours=QUIET_MAX_H):
                p["quiet"] = f"已经 {int((now - lt).total_seconds() // 3600)} 小时没收到任何买家消息（上一条：{last[5:16]}），可能是连接有问题，请打开闲鱼看一下。"
        except Exception:
            pass

    # 6) server resources
    try:
        mem = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in open("/proc/meminfo"))}
        if mem["MemAvailable"] < 200 * 1024:
            p["memory"] = f"服务器内存快用完了（剩 {mem['MemAvailable'] // 1024} MB）。"
    except Exception:
        pass
    s = os.statvfs("/")
    used = 100 - s.f_bavail * 100 // s.f_blocks
    if used >= 90:
        p["disk"] = f"服务器磁盘已用 {used}%，快满了。"
    return p


def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"open": {}, "pending": {}, "last_check": (datetime.now() - timedelta(minutes=6)).strftime("%F %T")}


def save(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


NEED_TWICE = {"im_down", "containers"}   # short blips (restart / reconnect) should not wake the owner
# Found in the log since the last check: one-off events. No 「已恢复」 for them; same event at most once per 2h,
# except a failed greeting, which is always sent (each one is a different buyer).
EVENTS = {"token_balance", "token_expired", "token_renew", "ai_api", "greeting", "slider", "risk"}


def main():
    if "--test" in sys.argv:
        print("FEISHU OK" if send("测试消息：服务器上的 24 小时监控已经装好了，以后出问题会直接发到这里。") else "FEISHU FAILED")
        return
    st = load()
    now_s = datetime.now().strftime("%F %T")
    since = st.get("last_check") or now_s
    probs = checks(since)
    st["last_check"] = now_s
    t = time.time()
    msgs = []
    pend = st.setdefault("pending", {})
    for k, text in probs.items():
        if k in NEED_TWICE and k not in st["open"] and not pend.get(k):
            pend[k] = 1
            continue
        pend.pop(k, None)
        if k in EVENTS:
            ev = st.setdefault("events", {})
            if k == "greeting" or t - ev.get(k, 0) >= REPEAT_S:
                msgs.append("❗" + text)
                ev[k] = t
            continue
        o = st["open"].get(k)
        if not o or t - o["sent"] >= REPEAT_S:
            msgs.append(("❗" if not o else "❗仍未解决：") + text)
            st["open"][k] = {"sent": t, "since": (o or {}).get("since", now_s), "text": text}
    for k in list(pend):
        if k not in probs:
            pend.pop(k)
    for k in list(st["open"]):
        if k not in probs:
            o = st["open"].pop(k)
            msgs.append(f"✅已恢复：{o['text'][:40]}…（{o['since'][5:16]} 开始）")
    prev_orders = (st.get("refund_seen"), st.get("complaint_last_id"))
    try:
        msgs += order_events(st)
    except Exception as e:
        print("order events failed:", type(e).__name__)
    today = now_s[:10]
    if "--heartbeat" in sys.argv or (int(now_s[11:13]) >= 9 and st.get("hb_day") != today):
        st["hb_day"] = today
        opened = "；".join(o["text"][:30] for o in st["open"].values())
        msgs.append("每日报平安：监控正常运行中。" + (f"目前未解决的问题：{opened}" if opened else "目前没有发现问题。"))
    if msgs:
        try:
            if not send("\n".join(msgs)):
                raise RuntimeError("feishu refused")
        except Exception as e:
            # nothing reached the owner: rescan the same log window next run and treat everything as unsent
            st["last_check"] = since
            if prev_orders[0] is not None:
                st["refund_seen"], st["complaint_last_id"] = prev_orders
            for k in probs:
                if k in st["open"] and st["open"][k]["sent"] == t:
                    st["open"][k]["sent"] = 0
                if st.get("events", {}).get(k) == t:
                    st["events"][k] = 0
            print("send failed:", type(e).__name__)
    save(st)
    print(now_s, "problems:", sorted(probs), "sent:", len(msgs))


if __name__ == "__main__":
    main()
