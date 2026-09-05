#!/usr/bin/env bash
# BackTest Studio 服务管理
#
#   bash scripts/ctl.sh start      后台启动前后端
#   bash scripts/ctl.sh stop       停止
#   bash scripts/ctl.sh restart    重启（改了 .env 或依赖后用这个）
#   bash scripts/ctl.sh status     谁在跑、健康不健康、AI 通没通
#   bash scripts/ctl.sh logs api   跟踪日志（api | web）
#   bash scripts/ctl.sh doctor     体检：依赖、端口、健康、是否在跑假数据
#   bash scripts/ctl.sh test       跑后端 + 前端测试
#
# 端口可覆盖：API_PORT=8001 WEB_PORT=5174 bash scripts/ctl.sh start
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN="$ROOT/.run"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
API_PID="$RUN/api.pid"
WEB_PID="$RUN/web.pid"
API_LOG="$RUN/api.log"
WEB_LOG="$RUN/web.log"

mkdir -p "$RUN"

# ── 输出 ────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_WARN=$'\033[33m'; C_DIM=$'\033[2m'; C_INFO=$'\033[36m'; C_OFF=$'\033[0m'
else
  C_OK=''; C_BAD=''; C_WARN=''; C_DIM=''; C_INFO=''; C_OFF=''
fi
say()  { printf '%s▸%s %s\n' "$C_INFO" "$C_OFF" "$1"; }
ok()   { printf '%s✓%s %s\n' "$C_OK" "$C_OFF" "$1"; }
bad()  { printf '%s✗%s %s\n' "$C_BAD" "$C_OFF" "$1"; }
warn() { printf '%s!%s %s\n' "$C_WARN" "$C_OFF" "$1"; }
dim()  { printf '%s  %s%s\n' "$C_DIM" "$1" "$C_OFF"; }

# ── 基础工具 ────────────────────────────────────────────────────────────
port_pid() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1; }
alive()    { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

pid_of() {  # pid_of api|web —— 先读 pid 文件，再回落到端口占用
  local f port
  case "$1" in
    api) f="$API_PID"; port="$API_PORT" ;;
    web) f="$WEB_PID"; port="$WEB_PORT" ;;
  esac
  local p=""
  [ -f "$f" ] && p="$(cat "$f" 2>/dev/null)"
  if alive "$p"; then echo "$p"; return 0; fi
  port_pid "$port"
}

api_health() { curl -fsS --max-time 3 "http://localhost:$API_PORT/api/health" 2>/dev/null; }

# ── 依赖 ────────────────────────────────────────────────────────────────
ensure_backend_deps() {
  cd "$BACKEND" || return 1
  if [ ! -x "venv/bin/python" ]; then
    say "创建 backend/venv"
    rm -rf venv
    python3 -m venv venv || { bad "python3 -m venv 失败"; return 1; }
  fi
  # 按 requirements.txt 的时间戳判断，而不是探几个 import：
  # 旧 venv 可能有 fastapi 却缺 slowapi，探测会漏过去。
  local stamp="venv/.requirements.stamp"
  if [ ! -f "$stamp" ] || [ requirements.txt -nt "$stamp" ]; then
    say "安装后端依赖"
    ./venv/bin/pip install -q --upgrade pip
    ./venv/bin/pip install -q -r requirements.txt || { bad "依赖安装失败"; return 1; }
    touch "$stamp"
  fi
  [ -f .env ] || { say "从 .env.example 创建 backend/.env"; cp .env.example .env; }
}

ensure_frontend_deps() {
  cd "$FRONTEND" || return 1
  if [ ! -d node_modules ]; then
    say "安装前端依赖"
    npm install --no-audit --no-fund || { bad "npm install 失败"; return 1; }
  fi
}

# ── start ───────────────────────────────────────────────────────────────
cmd_start() {
  local running=0
  alive "$(pid_of api)" && { warn "API 已在 :$API_PORT 运行（restart 可重启）"; running=1; }
  alive "$(pid_of web)" && { warn "UI 已在 :$WEB_PORT 运行（restart 可重启）"; running=1; }
  [ "$running" = 1 ] && return 1

  ensure_backend_deps || return 1

  say "启动 API :$API_PORT"
  cd "$BACKEND"
  nohup ./venv/bin/uvicorn app.main:app --reload --port "$API_PORT" >"$API_LOG" 2>&1 &
  echo $! >"$API_PID"

  # 等 API 真的能应答再起 UI。否则 UI 会对着一个死后端渲染演示数据，
  # 看不出任何区别——这正是之前那个 bug 的成因。
  local up=0
  for _ in $(seq 1 60); do
    api_health >/dev/null && { up=1; break; }
    alive "$(cat "$API_PID")" || break
    sleep 0.5
  done
  if [ "$up" != 1 ]; then
    bad "API 没能起来，日志最后 25 行："
    echo
    tail -25 "$API_LOG"
    kill "$(cat "$API_PID")" 2>/dev/null
    rm -f "$API_PID"
    return 1
  fi
  ok "API 就绪  http://localhost:$API_PORT/docs"

  ensure_frontend_deps || return 1
  say "启动 UI :$WEB_PORT"
  cd "$FRONTEND"
  VITE_API_PORT="$API_PORT" nohup npm run dev -- --port "$WEB_PORT" >"$WEB_LOG" 2>&1 &
  echo $! >"$WEB_PID"

  for _ in $(seq 1 40); do
    [ -n "$(port_pid "$WEB_PORT")" ] && break
    sleep 0.5
  done
  if [ -z "$(port_pid "$WEB_PORT")" ]; then
    bad "UI 没能起来，日志最后 25 行："
    tail -25 "$WEB_LOG"
    return 1
  fi
  ok "UI 就绪   http://localhost:$WEB_PORT"

  echo
  local llm; llm="$(api_health | grep -o '"llm_available":[a-z]*' | cut -d: -f2)"
  if [ "$llm" = "true" ]; then
    ok "AI 已接通（自然语言配置、逐层解读、Agent 调查走真模型）"
  else
    warn "AI 未接通：backend/.env 里没有 DEEPSEEK_API_KEY，AI 功能走确定性兜底"
  fi
  dim "日志：bash scripts/ctl.sh logs api|web"
}

# ── stop ────────────────────────────────────────────────────────────────
kill_one() {
  local name="$1" f="$2" port="$3"
  local p; p="$(pid_of "$name")"
  if ! alive "$p"; then rm -f "$f"; dim "$name 未在运行"; return 0; fi
  kill "$p" 2>/dev/null
  for _ in $(seq 1 20); do alive "$p" || break; sleep 0.25; done
  alive "$p" && kill -9 "$p" 2>/dev/null
  # vite / uvicorn --reload 会派生子进程，按端口收尾
  local stray; stray="$(port_pid "$port")"
  [ -n "$stray" ] && kill -9 "$stray" 2>/dev/null
  rm -f "$f"
  ok "$name 已停止"
}

cmd_stop() {
  kill_one web "$WEB_PID" "$WEB_PORT"
  kill_one api "$API_PID" "$API_PORT"
}

cmd_restart() { cmd_stop; echo; cmd_start; }

# ── status ──────────────────────────────────────────────────────────────
cmd_status() {
  local ap wp health
  ap="$(pid_of api)"; wp="$(pid_of web)"
  health="$(api_health)"

  if [ -n "$health" ]; then
    ok "API   :$API_PORT  pid ${ap:-?}  健康"
    local llm; llm="$(echo "$health" | grep -o '"llm_available":[a-z]*' | cut -d: -f2)"
    local model; model="$(echo "$health" | grep -o '"llm_model":"[^"]*"' | cut -d'"' -f4)"
    if [ "$llm" = "true" ]; then dim "AI 已接通 · ${model:-?}"; else dim "AI 未接通（走兜底）"; fi
  elif alive "$ap"; then
    warn "API   :$API_PORT  pid $ap  进程在但健康检查不通"
  else
    bad "API   :$API_PORT  未运行"
  fi

  if alive "$wp"; then
    ok "UI    :$WEB_PORT  pid $wp  http://localhost:$WEB_PORT"
  else
    bad "UI    :$WEB_PORT  未运行"
  fi

  # 最危险的组合：UI 活着而 API 死了 —— 页面会渲染演示数据
  if alive "$wp" && [ -z "$health" ]; then
    echo
    warn "UI 在跑但 API 不通：页面顶部会出现橙色「演示数据」横幅，"
    warn "所有数字都是假的。用 restart 修复。"
  fi
}

# ── logs ────────────────────────────────────────────────────────────────
cmd_logs() {
  case "${1:-api}" in
    api) tail -f "$API_LOG" ;;
    web) tail -f "$WEB_LOG" ;;
    *)   bad "用法：ctl.sh logs api|web"; return 1 ;;
  esac
}

# ── doctor ──────────────────────────────────────────────────────────────
cmd_doctor() {
  say "环境"
  command -v python3 >/dev/null && ok "python3 $(python3 --version 2>&1 | cut -d' ' -f2)" || bad "找不到 python3"
  command -v npm >/dev/null && ok "npm $(npm --version)" || bad "找不到 npm"

  echo; say "后端"
  if [ -x "$BACKEND/venv/bin/python" ]; then
    ok "venv 存在 · $("$BACKEND/venv/bin/python" --version 2>&1 | cut -d' ' -f2)"
    local missing=""
    for m in fastapi uvicorn slowapi numpy scipy sklearn pydantic openai; do
      "$BACKEND/venv/bin/python" -c "import $m" 2>/dev/null || missing="$missing $m"
    done
    [ -z "$missing" ] && ok "依赖齐全" || bad "缺少依赖：$missing（restart 会自动补装）"
  else
    bad "backend/venv 不存在（start 会自动创建）"
  fi
  if [ -f "$BACKEND/.env" ]; then
    grep -q "^DEEPSEEK_API_KEY=." "$BACKEND/.env" && ok "已配置 DEEPSEEK_API_KEY" || warn "未配置 DEEPSEEK_API_KEY（AI 走兜底）"
  else
    warn "backend/.env 不存在（start 会从 .env.example 创建）"
  fi

  echo; say "前端"
  [ -d "$FRONTEND/node_modules" ] && ok "node_modules 存在" || warn "node_modules 不存在（start 会自动安装）"

  echo; say "端口"
  local ap wp
  ap="$(port_pid "$API_PORT")"; wp="$(port_pid "$WEB_PORT")"
  if [ -n "$ap" ]; then
    if api_health >/dev/null; then ok ":$API_PORT 被本项目 API 占用且健康"
    else warn ":$API_PORT 被 pid $ap 占用，但不是健康的本项目 API"; fi
  else dim ":$API_PORT 空闲"; fi
  [ -n "$wp" ] && ok ":$WEB_PORT 被 pid $wp 占用" || dim ":$WEB_PORT 空闲"

  echo; say "数据真实性"
  local h; h="$(api_health)"
  if [ -z "$h" ]; then
    bad "API 不通 —— 此时打开 UI，看到的全部是演示假数据"
  else
    local rid
    rid="$(curl -fsS --max-time 20 -X POST "http://localhost:$API_PORT/api/experiments/run" \
      -H 'content-type: application/json' \
      -d '{"champion":"v2.2","challenger":"v2.3","beta":null,"sample_id":"consumer_2024q1q2","language":"zh"}' \
      2>/dev/null | grep -o '"run_id":"[^"]*"' | cut -d'"' -f4)"
    if [ -z "$rid" ]; then
      bad "回测接口调用失败"
    elif [ "$rid" = "run-20241115-001" ]; then
      bad "返回了演示数据的 run_id —— 不正常，请检查后端"
    else
      ok "回测接口返回真实 run_id：$rid"
    fi
  fi
}

# ── test ────────────────────────────────────────────────────────────────
cmd_test() {
  say "后端测试"
  cd "$BACKEND" && RATE_LIMIT_ENABLED=0 ./venv/bin/python -m pytest tests/ -q
  echo; say "前端测试"
  cd "$FRONTEND" && npm test
}

# ── dispatch ────────────────────────────────────────────────────────────
case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs "${2:-api}" ;;
  doctor)  cmd_doctor ;;
  test)    cmd_test ;;
  *)
    cat <<EOF
BackTest Studio 服务管理

  bash scripts/ctl.sh start      后台启动前后端（等健康检查通过才算成功）
  bash scripts/ctl.sh stop       停止
  bash scripts/ctl.sh restart    重启 —— 改了 .env 或依赖后用这个
  bash scripts/ctl.sh status     当前状态 + AI 是否接通
  bash scripts/ctl.sh logs api   跟踪日志（api | web）
  bash scripts/ctl.sh doctor     体检，含"是不是在跑假数据"的判定
  bash scripts/ctl.sh test       跑测试

  端口覆盖：API_PORT=8001 WEB_PORT=5174 bash scripts/ctl.sh start
  前台开发（Ctrl-C 停）：bash scripts/dev.sh
EOF
    ;;
esac
