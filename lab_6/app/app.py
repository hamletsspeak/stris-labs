import json
import os
import random
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Dict, Generator, Optional

import psycopg2
import redis
import requests
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse


ROLE = os.getenv("ROLE", "gateway")
SERVICE_NAME = os.getenv("SERVICE_NAME", ROLE)
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8080"))
DISCOVERY_URL = os.getenv("DISCOVERY_URL", "http://discovery:8500")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@postgres:5432/app")
BACKPRESSURE_LIMIT = int(os.getenv("BACKPRESSURE_LIMIT", "100"))
PAYMENT_FAILURE_RATE = float(os.getenv("PAYMENT_FAILURE_RATE", "0.30"))

STREAM_KEY = "orders:commands"
STREAM_GROUP = "order-workers"
EVENT_CHANNEL = "events"
CACHE_TAG_PREFIX = "cache:tag:"


class CircuitBreaker:
    def __init__(self, fail_threshold: int = 3, open_seconds: int = 15):
        self.fail_threshold = fail_threshold
        self.open_seconds = open_seconds
        self.failures = 0
        self.state = "closed"
        self.opened_at = 0.0

    def can_call(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if (time.time() - self.opened_at) >= self.open_seconds:
                self.state = "half_open"
                return True
            return False
        return True

    def on_success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def on_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.state = "open"
            self.opened_at = time.time()


circuit_breaker = CircuitBreaker()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


@contextmanager
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def ensure_schema() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS orders (
        id UUID PRIMARY KEY,
        user_id INTEGER NOT NULL,
        amount NUMERIC(12,2) NOT NULL,
        status VARCHAR(32) NOT NULL,
        idempotency_key VARCHAR(128) UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders (user_id);
    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
    """
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def set_order_status(order_id: str, status: str) -> Dict:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orders
                SET status = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id::text, user_id, amount::float8, status, updated_at::text
                """,
                (status, order_id),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise ValueError(f"Order {order_id} not found")

    return {
        "id": row[0],
        "user_id": row[1],
        "amount": float(row[2]),
        "status": row[3],
        "updated_at": row[4],
    }


def get_order(order_id: str) -> Optional[Dict]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, user_id, amount::float8, status, created_at::text, updated_at::text
                FROM orders
                WHERE id = %s
                """,
                (order_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "amount": float(row[2]),
        "status": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def create_order(user_id: int, amount: float, idem_key: Optional[str]) -> Dict:
    order_id = str(uuid.uuid4())

    with db_conn() as conn:
        with conn.cursor() as cur:
            if idem_key:
                cur.execute(
                    """
                    SELECT id::text, user_id, amount::float8, status, created_at::text, updated_at::text
                    FROM orders
                    WHERE idempotency_key = %s
                    """,
                    (idem_key,),
                )
                existing = cur.fetchone()
                if existing:
                    return {
                        "id": existing[0],
                        "user_id": existing[1],
                        "amount": float(existing[2]),
                        "status": existing[3],
                        "created_at": existing[4],
                        "updated_at": existing[5],
                        "idempotent_replay": True,
                    }

            cur.execute(
                """
                INSERT INTO orders (id, user_id, amount, status, idempotency_key)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id::text, user_id, amount::float8, status, created_at::text, updated_at::text
                """,
                (order_id, user_id, amount, "PENDING", idem_key),
            )
            created = cur.fetchone()
        conn.commit()

    return {
        "id": created[0],
        "user_id": created[1],
        "amount": float(created[2]),
        "status": created[3],
        "created_at": created[4],
        "updated_at": created[5],
        "idempotent_replay": False,
    }


def project_order_to_cache(r: redis.Redis, order: Dict) -> None:
    cache_key = f"order:view:{order['id']}"
    old = r.hgetall(cache_key)
    old_version = int(old.get("version", "0")) if old else 0
    version = old_version + 1
    etag = f'W/"{version}"'
    tag = f"user:{order['user_id']}"

    data = {
        "id": order["id"],
        "user_id": str(order["user_id"]),
        "amount": str(order["amount"]),
        "status": order["status"],
        "updated_at": order.get("updated_at", now_iso()),
        "version": str(version),
        "etag": etag,
        "cache_tag": tag,
    }
    r.hset(cache_key, mapping=data)
    r.expire(cache_key, 600)
    r.sadd(f"{CACHE_TAG_PREFIX}{tag}", order["id"])
    r.expire(f"{CACHE_TAG_PREFIX}{tag}", 600)


def invalidate_tag(r: redis.Redis, tag: str) -> None:
    key = f"{CACHE_TAG_PREFIX}{tag}"
    ids = r.smembers(key)
    for order_id in ids:
        r.delete(f"order:view:{order_id}")
    r.delete(key)


def resolve_service(service_name: str) -> str:
    response = requests.get(f"{DISCOVERY_URL}/resolve/{service_name}", timeout=2)
    response.raise_for_status()
    return response.json()["url"]


def publish_event(r: redis.Redis, event: Dict) -> None:
    r.publish(EVENT_CHANNEL, json.dumps(event))


def heartbeat_loop() -> None:
    payload = {
        "service": SERVICE_NAME,
        "instance": f"{SERVICE_NAME}-{SERVICE_HOST}-{SERVICE_PORT}",
        "url": f"http://{SERVICE_HOST}:{SERVICE_PORT}",
    }
    while True:
        try:
            requests.post(f"{DISCOVERY_URL}/register", json=payload, timeout=2)
        except Exception:
            pass
        time.sleep(5)


def start_heartbeat_thread() -> None:
    import threading

    thread = threading.Thread(target=heartbeat_loop, daemon=True)
    thread.start()


def app_with_startup(title: str, startup_fn) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        startup_fn()
        yield

    return FastAPI(title=title, lifespan=lifespan)


def create_discovery_app() -> FastAPI:
    app = FastAPI(title="discovery-service")
    registry: Dict[str, Dict[str, Dict]] = {}

    @app.post("/register")
    def register(payload: Dict):
        service = payload["service"]
        instance = payload["instance"]
        url = payload["url"]

        registry.setdefault(service, {})[instance] = {
            "url": url,
            "last_seen": time.time(),
        }
        return {"status": "ok", "time": now_iso()}

    @app.get("/resolve/{service}")
    def resolve(service: str):
        ttl_seconds = 15
        instances = registry.get(service, {})
        alive = [
            meta["url"]
            for _, meta in instances.items()
            if (time.time() - meta["last_seen"]) <= ttl_seconds
        ]
        if not alive:
            raise HTTPException(status_code=404, detail=f"No healthy instances for {service}")

        chosen = random.choice(alive)
        return {"service": service, "url": chosen, "healthy_instances": len(alive)}

    @app.get("/services")
    def services():
        return registry

    @app.get("/health")
    def health():
        return {"status": "up", "service": "discovery"}

    return app


def create_order_app() -> FastAPI:
    def startup_event():
        ensure_schema()
        start_heartbeat_thread()
    app = app_with_startup("order-service", startup_event)

    @app.post("/orders")
    def create_order_endpoint(body: Dict, idempotency_key: Optional[str] = Header(default=None)):
        r = redis_client()
        queue_depth = r.xlen(STREAM_KEY) if r.exists(STREAM_KEY) else 0
        if queue_depth > BACKPRESSURE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Backpressure: queue depth {queue_depth} > {BACKPRESSURE_LIMIT}",
            )

        user_id = int(body["user_id"])
        amount = float(body["amount"])
        order = create_order(user_id, amount, idempotency_key)

        if order["status"] == "PENDING":
            r.xadd(
                STREAM_KEY,
                {
                    "order_id": order["id"],
                    "user_id": str(order["user_id"]),
                    "amount": str(order["amount"]),
                },
            )
            publish_event(
                r,
                {
                    "type": "order_created",
                    "order_id": order["id"],
                    "status": "PENDING",
                    "at": now_iso(),
                },
            )

        project_order_to_cache(r, order)
        return {
            "order": order,
            "queue_depth": queue_depth,
            "cqrs": "command accepted, read model in redis",
        }

    @app.get("/orders/{order_id}")
    def get_order_endpoint(order_id: str, request: Request):
        r = redis_client()
        cache_key = f"order:view:{order_id}"

        try:
            cached = r.hgetall(cache_key)
        except Exception:
            cached = {}

        if cached:
            etag = cached.get("etag", "")
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304)

            return JSONResponse(
                {
                    "id": cached["id"],
                    "user_id": int(cached["user_id"]),
                    "amount": float(cached["amount"]),
                    "status": cached["status"],
                    "version": int(cached["version"]),
                    "cache_tag": cached["cache_tag"],
                    "degraded": False,
                },
                headers={"ETag": etag},
            )

        order = get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        try:
            project_order_to_cache(r, order)
            cached_after = r.hgetall(cache_key)
            etag = cached_after.get("etag", "")
        except Exception:
            etag = ""

        return JSONResponse(
            {
                **order,
                "degraded": True,
                "degraded_reason": "read fallback to postgres",
            },
            headers={"ETag": etag} if etag else {},
        )

    @app.get("/analytics/daily")
    def analytics_daily():
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT created_at::date::text, amount::float8, status
                    FROM orders
                    """
                )
                rows = cur.fetchall()

        mapped = []
        for day, amount, status in rows:
            value = amount if status == "PAID" else 0.0
            mapped.append((day, value))

        reduced: Dict[str, float] = {}
        for day, value in mapped:
            reduced[day] = reduced.get(day, 0.0) + value

        return {
            "description": "MapReduce style: map(order -> (day, paid_amount)), reduce(sum by day)",
            "result": reduced,
        }

    @app.get("/health")
    def health():
        return {"status": "up", "service": "order"}

    return app


def create_payment_app() -> FastAPI:
    def startup_event():
        start_heartbeat_thread()
    app = app_with_startup("payment-service", startup_event)

    @app.post("/charge")
    def charge(body: Dict):
        amount = float(body["amount"])
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")

        if random.random() < PAYMENT_FAILURE_RATE:
            raise HTTPException(status_code=503, detail="Temporary payment provider error")

        return {
            "ok": True,
            "transaction_id": str(uuid.uuid4()),
            "charged_at": now_iso(),
        }

    @app.get("/health")
    def health():
        return {"status": "up", "service": "payment"}

    return app


def create_gateway_app() -> FastAPI:
    def startup_event():
        start_heartbeat_thread()
    app = app_with_startup("api-gateway", startup_event)

    @app.post("/api/orders")
    def create_order_via_gateway(body: Dict, idempotency_key: Optional[str] = Header(default=None)):
        order_url = resolve_service("order")
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        response = requests.post(f"{order_url}/orders", json=body, headers=headers, timeout=5)
        return JSONResponse(status_code=response.status_code, content=response.json())

    @app.get("/api/orders/{order_id}")
    def get_order_via_gateway(order_id: str, if_none_match: Optional[str] = Header(default=None)):
        order_url = resolve_service("order")
        headers = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match

        response = requests.get(f"{order_url}/orders/{order_id}", headers=headers, timeout=5)
        if response.status_code == 304:
            return Response(status_code=304)

        content = response.json()
        return JSONResponse(
            status_code=response.status_code,
            content=content,
            headers={"ETag": response.headers.get("ETag", "")},
        )

    @app.get("/api/orders/{order_id}/status")
    def polling_status(order_id: str):
        order_url = resolve_service("order")
        response = requests.get(f"{order_url}/orders/{order_id}", timeout=5)
        payload = response.json()
        return {"mode": "polling", "order_id": order_id, "status": payload.get("status")}

    @app.get("/api/orders/{order_id}/status/long-poll")
    def long_poll_status(order_id: str, timeout_seconds: int = 20, current_status: str = ""):
        order_url = resolve_service("order")
        started = time.time()
        while (time.time() - started) < timeout_seconds:
            response = requests.get(f"{order_url}/orders/{order_id}", timeout=5)
            payload = response.json()
            status = payload.get("status")
            if status != current_status:
                return {
                    "mode": "long-polling",
                    "order_id": order_id,
                    "status": status,
                    "changed": True,
                }
            time.sleep(1)

        return {
            "mode": "long-polling",
            "order_id": order_id,
            "status": current_status,
            "changed": False,
        }

    @app.get("/api/orders/{order_id}/status/stream")
    def stream_status(order_id: str):
        def event_stream() -> Generator[str, None, None]:
            order_url = resolve_service("order")
            last = ""
            for _ in range(30):
                response = requests.get(f"{order_url}/orders/{order_id}", timeout=5)
                payload = response.json()
                status = payload.get("status", "UNKNOWN")
                if status != last:
                    last = status
                    yield f"event: status\ndata: {json.dumps({'order_id': order_id, 'status': status})}\n\n"
                time.sleep(1)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/health")
    def health():
        return {"status": "up", "service": "gateway"}

    return app


def run_worker() -> None:
    print("[worker] starting")
    ensure_schema()
    r = redis_client()

    try:
        r.xgroup_create(STREAM_KEY, STREAM_GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    while True:
        messages = r.xreadgroup(
            groupname=STREAM_GROUP,
            consumername=f"worker-{SERVICE_HOST}",
            streams={STREAM_KEY: ">"},
            count=1,
            block=5000,
        )

        if not messages:
            continue

        _, entries = messages[0]
        for message_id, fields in entries:
            order_id = fields["order_id"]
            order = get_order(order_id)
            if not order:
                r.xack(STREAM_KEY, STREAM_GROUP, message_id)
                continue

            if order["status"] != "PENDING":
                r.xack(STREAM_KEY, STREAM_GROUP, message_id)
                continue

            if not circuit_breaker.can_call():
                set_order_status(order_id, "REVIEW")
                publish_event(
                    r,
                    {
                        "type": "fallback",
                        "order_id": order_id,
                        "status": "REVIEW",
                        "reason": "circuit_open",
                        "at": now_iso(),
                    },
                )
                r.xack(STREAM_KEY, STREAM_GROUP, message_id)
                continue

            max_attempts = 5
            success = False
            for attempt in range(1, max_attempts + 1):
                try:
                    payment_url = resolve_service("payment")
                    resp = requests.post(
                        f"{payment_url}/charge",
                        json={"order_id": order_id, "amount": order["amount"]},
                        timeout=3,
                    )
                    if resp.status_code == 200:
                        success = True
                        circuit_breaker.on_success()
                        break
                    circuit_breaker.on_failure()
                except Exception:
                    circuit_breaker.on_failure()

                sleep_for = min(2 ** attempt, 16)
                time.sleep(sleep_for)

            if success:
                updated = set_order_status(order_id, "PAID")
                project_order_to_cache(r, updated)
                invalidate_tag(r, f"user:{updated['user_id']}")
                publish_event(
                    r,
                    {
                        "type": "order_paid",
                        "order_id": order_id,
                        "status": "PAID",
                        "at": now_iso(),
                    },
                )
            else:
                updated = set_order_status(order_id, "REVIEW")
                project_order_to_cache(r, updated)
                publish_event(
                    r,
                    {
                        "type": "graceful_degradation",
                        "order_id": order_id,
                        "status": "REVIEW",
                        "reason": "payment_temporary_failure",
                        "at": now_iso(),
                    },
                )

            r.xack(STREAM_KEY, STREAM_GROUP, message_id)


def run_notifier() -> None:
    print("[notifier] listening pub/sub")
    r = redis_client()
    pubsub = r.pubsub()
    pubsub.subscribe(EVENT_CHANNEL)

    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        data = msg["data"]
        print(f"[notifier] event={data}", flush=True)


app = None
if ROLE == "discovery":
    app = create_discovery_app()
elif ROLE == "order":
    app = create_order_app()
elif ROLE == "payment":
    app = create_payment_app()
elif ROLE == "gateway":
    app = create_gateway_app()


if __name__ == "__main__":
    if app is not None:
        import uvicorn

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=SERVICE_PORT,
            access_log=False,
            log_level="warning",
        )
    elif ROLE == "worker":
        run_worker()
    elif ROLE == "notifier":
        run_notifier()
    else:
        raise RuntimeError(f"Unsupported ROLE={ROLE}")
