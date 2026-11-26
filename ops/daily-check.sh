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
SL=/opt/xianyu-local-modified/data/logs/scheduler; SD=$(cat $(ls -t $SL/scheduler*.log | head -2) 2>/dev/null | awk -v s="$S" 'substr($0,1,19) >= s' | grep '定时补评价')
echo "daily_rate_batch(20:00): rated=$(echo "$SD" | grep -c '评价成功')  not_yet_completed=$(echo "$SD" | grep -c '不可评价: 订单未交易成功')  thanks_msg_failed=$(echo "$SD" | grep -c '好评后消息发送失败')"
echo "risk_words=$(echo "$D" | grep -cE '违规|处罚|封禁|账号异常|限制登录|风险账号')"
echo "expired_token_in_use=$(echo "$D" | grep -c '暂时使用已过期Token缓存')"
SR=$(cat $(ls -t $SL/scheduler*.log | head -2) 2>/dev/null | awk -v s="$S" 'substr($0,1,19) >= s' | sort | grep -E 'Token续期任务|im_token_api')
echo "token_balance_fail=$(( $(echo "$D" | grep -c '余额不足') + $(echo "$SR" | grep -c '余额不足') ))"
echo "token_renew_fail=$(echo "$SR" | grep -c '续期未成功')  token_renew_fail_last=$(echo "$SR" | grep '续期未成功' | tail -1 | cut -c1-16)  token_renew_ok_last=$(echo "$SR" | grep '远程接口取Token成功' | tail -1 | cut -c1-16)"
SO=$(cat $(ls -t $SL/scheduler*.log | head -2) 2>/dev/null | awk -v s="$S" 'substr($0,1,19) >= s' | sort | grep '【定时获取闲鱼订单】执行完成')
echo "order_sync_runs=$(echo "$SO" | grep -c '成功1/')  order_sync_fail=$(echo "$SO" | grep -vc '成功1/')  order_sync_ok_last=$(echo "$SO" | grep '成功1/' | tail -1 | cut -c1-16)  newest_order=$(docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xianyu_data -N -e "select max(placed_at) from xy_orders" 2>/dev/null')"
echo "signed_greeting_sent=$(echo "$D" | grep -cE '签收问候(已发送|：订单.*已发送)')  signed_greeting_failed=$(echo "$D" | grep -cE '签收问候：订单.*(重试3次都没发出去|等了15分钟)')"
echo "last_buyer_msg=$(docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xianyu_data -N -e "select max(source_message_time) from xy_auto_reply_message_logs where decision_reason not in (\"self_message\",\"system_message\")" 2>/dev/null')"
echo "== latest risk lines (last 24h)"
echo "$D" | grep -E '检测到需要滑块验证|AccessDenied|违规|处罚|封禁|账号异常|发送消息失败' | tail -5 | cut -c1-200
echo "== buyer messages in last 24h without reply (failed)"
docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 xianyu_data -N -e "select count(*) from xy_auto_reply_message_logs where source_message_time >= now() - interval 24 hour and process_status=\"failed\"" 2>/dev/null'
