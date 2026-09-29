import contextvars
import logging
import time
from typing import Any, Dict, Optional
from backend.core.config import settings

logger = logging.getLogger("telemetry")

_telemetry_ctx: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "_telemetry_ctx", default=None
)

def get_db_env_name() -> str:
    url = (settings.SUPABASE_URL or "").lower()
    if "kcwowusanrtvccmipjzu" in url:
        return "live_db (kcwowusanrtvccmipjzu)"
    elif "wgpxmvrbbgpzkomdutlk" in url:
        return "test_db (wgpxmvrbbgpzkomdutlk)"
    elif "localhost" in url or "127.0.0.1" in url:
        return "local_db"
    return "supabase_db"

def start_request_telemetry(
    request_id: str,
    path: str,
    method: str,
    user_id: Optional[str] = None,
    mobile_client_time_ms: Optional[float] = None
) -> Dict[str, Any]:
    ctx_data: Dict[str, Any] = {
        "request_id": request_id,
        "path": path,
        "method": method,
        "user_id": user_id or "Anonymous",
        "db_env": get_db_env_name(),
        "start_perf": time.perf_counter(),
        "mobile_client_time_ms": mobile_client_time_ms,
        "db_queries": [],
        "db_http_request_count": 0,
        "db_total_time_ms": 0.0,
    }
    _telemetry_ctx.set(ctx_data)
    return ctx_data

def get_current_telemetry() -> Optional[Dict[str, Any]]:
    return _telemetry_ctx.get()

def record_db_query(method: str, url: str, duration_ms: float, status_code: int) -> None:
    ctx = _telemetry_ctx.get()
    if ctx is None:
        return

    ctx["db_http_request_count"] += 1
    ctx["db_total_time_ms"] += duration_ms

    target = url
    if "/rest/v1/" in url:
        target = url.split("/rest/v1/")[-1]
    elif "/auth/v1/" in url:
        target = "auth/" + url.split("/auth/v1/")[-1]

    if len(target) > 70:
        target = target[:67] + "..."

    ctx["db_queries"].append({
        "index": ctx["db_http_request_count"],
        "method": method.upper(),
        "target": target,
        "duration_ms": duration_ms,
        "status_code": status_code
    })

def set_telemetry_user(user_id: str) -> None:
    ctx = _telemetry_ctx.get()
    if ctx and user_id:
        ctx["user_id"] = user_id

def _pad(text: str, width: int = 76) -> str:
    if len(text) > width:
        text = text[:width - 3] + "..."
    return f"│ {text.ljust(width)} │"

def log_telemetry_summary(status_code: int, response_size_bytes: int = 0) -> None:
    ctx = _telemetry_ctx.get()
    if not ctx:
        return

    end_perf = time.perf_counter()
    backend_total_ms = (end_perf - ctx["start_perf"]) * 1000.0
    db_total_ms = ctx["db_total_time_ms"]
    db_count = ctx["db_http_request_count"]
    server_logic_ms = max(0.0, backend_total_ms - db_total_ms)

    db_pct = (db_total_ms / backend_total_ms * 100.0) if backend_total_ms > 0 else 0.0
    server_pct = (server_logic_ms / backend_total_ms * 100.0) if backend_total_ms > 0 else 0.0

    mobile_time_ms = ctx.get("mobile_client_time_ms")
    mobile_network_ms = None
    if mobile_time_ms:
        try:
            current_now_ms = time.time() * 1000.0
            mobile_network_ms = max(0.0, current_now_ms - float(mobile_time_ms))
        except (ValueError, TypeError):
            mobile_network_ms = None

    if response_size_bytes >= 1024 * 1024:
        size_str = f"{response_size_bytes / (1024 * 1024):.2f} MB"
    elif response_size_bytes >= 1024:
        size_str = f"{response_size_bytes / 1024:.2f} KB"
    else:
        size_str = f"{response_size_bytes} B"

    is_slow = backend_total_ms > 500.0 or db_count > 5
    status_icon = "🟢 OK" if status_code < 400 else "🔴 ERR"
    speed_icon = "⚠️ SLOW" if is_slow else "⚡ FAST"

    w = 76
    lines = [
        "",
        "┌" + "─" * w + "┐",
        _pad(f"⏱️  SPEED & QUERY LATENCY TELEMETRY | {status_icon} ({status_code}) | {speed_icon}", w),
        "├" + "─" * w + "┤",
        _pad(f"📌 Request ID       : {ctx['request_id']}", w),
        _pad(f"🛣️  Path & Method   : {ctx['method']} {ctx['path']}", w),
        _pad(f"👤 User ID          : {ctx['user_id']}", w),
        _pad(f"🗄️  DB Environment  : {ctx['db_env']}", w),
        _pad(f"📦 Response Size    : {size_str}", w),
        "├" + "─" * w + "┤",
        _pad("📊 SPEED BREAKDOWN:", w),
    ]

    if mobile_network_ms is not None:
        lines.append(_pad(f"  📱 Mobile Client -> Backend Transport : {mobile_network_ms:.2f} ms", w))

    lines.extend([
        _pad(f"  ⚙️  Backend Execution Total          : {backend_total_ms:.2f} ms", w),
        _pad(f"      ├─ 🗄️ Database Execution        : {db_total_ms:.2f} ms ({db_pct:.1f}% of backend)", w),
        _pad(f"      └─ 💻 Backend Server Logic      : {server_logic_ms:.2f} ms ({server_pct:.1f}% of backend)", w),
        "├" + "─" * w + "┤",
        _pad("🗄️  DATABASE RESOLUTION TELEMETRY:", w),
        _pad(f"  • Total HTTP Requests Resolved in DB : {db_count} request(s)", w),
    ])

    if db_count > 0:
        avg_db_latency = db_total_ms / db_count
        lines.append(_pad(f"  • Average DB Request Latency         : {avg_db_latency:.2f} ms", w))
        lines.append(_pad("  • DB Query Execution Log:", w))
        for q in ctx["db_queries"]:
            lines.append(_pad(f"    [{q['index']}] {q['method']} {q['target']} -> {q['status_code']} ({q['duration_ms']:.2f} ms)", w))
    else:
        lines.append(_pad("  • DB Query Execution Log            : [0 DB Queries Executed (Cached/Static)]", w))

    lines.extend([
        "└" + "─" * w + "┘",
        ""
    ])

    logger.info("\n".join(lines))
