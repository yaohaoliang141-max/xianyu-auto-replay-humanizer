#!/bin/bash
# Read-only daily health/risk check for the Xianyu auto-reply server. Changes nothing.
L=/opt/xianyu-local-modified/data/logs/websocket/websocket.log
S=$(date -d '24 hours ago' '+%F %T')   # only the last 24 hours
echo "== server"; uptime; free -m | sed -n 2,3p; df -h / | tail -1
echo "== containers"; docker ps --format '{{.Names}} {{.Status}} {{.Image}}'
echo "== account flags"
docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xianyu_data -N -e "select status, ifnull(disable_reason,\"-\"), auto_red_flower, scheduled_rate, reply_delay_seconds, last_refresh_at from xy_accounts" 2>/dev/null'
D=$(awk -v s="$S" 'substr($0,1,19) >= s' $L 2>/dev/null)
echo "== last 24h (since $S)"
echo "slider_challenges=$(echo "$D" | grep -c '检测到需要滑块验证')"
echo "user_validate=$(echo "$D" | grep -c 'FAIL_SYS_USER_VALIDATE')"
echo "disconnects=$(echo "$D" | grep -cE '连接状态: connected → (disconnected|reconnecting)')"
echo "ai_replies=$(echo "$D" | grep -c 'AI回复生成成功')"
echo "ai_api_errors=$(echo "$D" | grep -cE 'AccessDenied|PermissionDenied|ai_reply_engine.*(API调用失败|Error code|失败)')"
echo "send_failures=$(echo "$D" | grep -cE '发送消息失败|send_failed')"
SD=$(awk -v s="$S" 'substr($0,1,19) >= s' /opt/xianyu-local-modified/data/logs/scheduler/scheduler.log 2>/dev/null | grep '定时补评价')
echo "daily_rate_batch(20:00): rated=$(echo "$SD" | grep -c '评价成功')  not_yet_completed=$(echo "$SD" | grep -c '订单未交易成功')  thanks_msg_failed=$(echo "$SD" | grep -c '好评后消息发送失败')"
echo "risk_words=$(echo "$D" | grep -cE '违规|处罚|封禁|账号异常|限制登录|风险账号')"
echo "== latest risk lines (last 24h)"
echo "$D" | grep -E '检测到需要滑块验证|AccessDenied|违规|处罚|封禁|账号异常|发送消息失败' | tail -5 | cut -c1-200
echo "== buyer messages in last 24h without reply (failed)"
docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 xianyu_data -N -e "select count(*) from xy_auto_reply_message_logs where source_message_time >= now() - interval 24 hour and process_status=\"failed\"" 2>/dev/null'
