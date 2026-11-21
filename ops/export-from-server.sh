#!/bin/bash
# Run ON THE SERVER. Builds /tmp/gh-export.tgz = what is live now, minus secrets/data,
# then refuses (exit 3) if any real secret value or cookie is found in it.
set -euo pipefail
B=/opt/xianyu-local-modified
E=/tmp/gh-export
rm -rf $E /tmp/gh-export.tgz; mkdir -p $E

# 1. source tree from the host (no VCS / deps / build output / runtime data)
tar -C $B --exclude=.git --exclude=node_modules --exclude=dist --exclude=__pycache__ --exclude='*.pyc' \
    --exclude=browser_data --exclude=logs --exclude='*.egg-info' --exclude='static/uploads' --exclude='backups' \
    -cf - app | tar -C $E -xf -

# 2. overlay code from the images that are running right now (images, not containers: no mounted data)
img() { docker inspect "$1" --format '{{.Config.Image}}'; }
WS=$(img xianyu-ecs-websocket-1); SC=$(img xianyu-ecs-scheduler-1); BW=$(img xianyu-ecs-backend-web-1)
echo "live images: websocket=$WS scheduler=$SC backend-web=$BW"
take() {  # image, dirs...
  local cid; cid=$(docker create "$1"); shift
  for d in "$@"; do rm -rf "$E/app/$d"; docker cp -q "$cid:/app/$d" "$E/app/$d"; done
  docker rm "$cid" >/dev/null
}
take "$WS" common websocket launcher
take "$SC" scheduler
take "$BW" backend-web
find $E -name __pycache__ -type d -prune -exec rm -rf {} + ; find $E -name '*.pyc' -delete
find $E -type d \( -name browser_data -o -name logs -o -name backups \) -prune -exec rm -rf {} +

# 3. deployment files + templates + live prompt
mkdir -p $E/scripts $E/prompts
cp $B/scripts/compose.yaml $B/scripts/Dockerfile $B/scripts/cloud_entry.py $B/scripts/cloud_health.py $E/scripts/
cp $B/requirements.lock.txt $B/.dockerignore $E/
printf 'MYSQL_ROOT_PASSWORD=\nMYSQL_DATABASE=xianyu_data\nMYSQL_USER=xianyu\nMYSQL_PASSWORD=\nREDIS_PASSWORD=\nNGINX_IMAGE=nginx:stable-alpine\n' > $E/infra.env.example
python3 - <<'PY'
import json
def blank(v):
    if isinstance(v, dict): return {k: blank(x) for k, x in v.items()}
    if isinstance(v, list): return []
    if isinstance(v, (bool, int, float)): return v
    return ""
d = json.load(open("/opt/xianyu-local-modified/runtime-settings.json"))
json.dump(blank(d), open("/tmp/gh-export/runtime-settings.example.json", "w"), ensure_ascii=False, indent=2)
PY
q() { docker exec xianyu-ecs-mysql-1 sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 xianyu_data -N -B --raw -e "$0" 2>/dev/null' "$1"; }
q "select json_unquote(json_extract(metadata,'$.ai_reply_settings.custom_prompts')) from xy_accounts where id=1" \
  | python3 -c "import json,sys;print(json.loads(sys.stdin.read())['default'])" > $E/prompts/ai-reply-prompt.txt

# 4. secret scan: real values (never printed) + cookie patterns
S=$(mktemp -d); chmod 700 $S
grep -E '^(MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|REDIS_PASSWORD)=' $B/infra.env | while IFS='=' read -r k v; do printf '%s' "$v" > "$S/env_$k"; done
q "select json_unquote(json_extract(metadata,'$.ai_reply_settings.api_key')) from xy_accounts" | tr -d '\n' > $S/ai_api_key
q "select ifnull(login_password,'') from xy_accounts" | tr -d '\n' > $S/login_password
q "select ifnull(proxy_pass,'') from xy_accounts" | tr -d '\n' > $S/proxy_pass
q "select cookie from xy_accounts" | tr ';' '\n' | sed 's/^ *//' | awk -F= 'length($2)>=12 {print $1"\t"substr($0, index($0,"=")+1)}' \
  | while IFS=$'\t' read -r k v; do printf '%s' "$v" > "$S/cookie_$(echo "$k" | tr -c 'a-zA-Z0-9_' '_')"; done
q "select \`key\`, value from xy_system_settings where \`key\` regexp 'secret|token|key|password' and \`key\` <> 'token.remote_url' and length(value) >= 8" \
  | while IFS=$'\t' read -r k v; do printf '%s' "$v" > "$S/sys_$(echo "$k" | tr -c 'a-zA-Z0-9_' '_')"; done
leaks=0
for f in $S/*; do
  v=$(cat "$f"); [ ${#v} -ge 6 ] || continue
  if grep -rqF -- "$v" $E; then echo "LEAK: $(basename "$f") in $(grep -rlF -- "$v" $E | head -3 | tr '\n' ' ')"; leaks=$((leaks+1)); fi
done
rm -rf $S
for p in 'cookie2=[A-Za-z0-9]' '_m_h5_tk=[A-Za-z0-9]' 'unb=[0-9]{6}' 'sk-[A-Za-z0-9]{20,}' '47\.118\.23\.223' '2211308660542'; do
  if grep -rqIE -- "$p" $E; then echo "PATTERN: $p in $(grep -rlIE -- "$p" $E | head -3 | tr '\n' ' ')"; leaks=$((leaks+1)); fi
done
if [ $leaks -gt 0 ]; then echo "REFUSING: $leaks problem(s) found"; rm -rf $E; exit 3; fi
tar -C $E -czf /tmp/gh-export.tgz . && rm -rf $E
echo "OK: /tmp/gh-export.tgz $(du -h /tmp/gh-export.tgz | cut -f1), secret scan clean"
