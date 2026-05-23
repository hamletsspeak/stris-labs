import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pika
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "outbox_demo")
DB_USER = os.getenv("DB_USER", "demo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "demo")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
OUTBOX_QUEUE = os.getenv("OUTBOX_QUEUE", "orders.events")
APP_ROLE = os.getenv("APP_ROLE", "api")


def db_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


@contextmanager
def rabbit_channel():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
    )
    channel = connection.channel()
    channel.queue_declare(queue=OUTBOX_QUEUE, durable=True)
    try:
        yield channel
    finally:
        connection.close()


def init_schema():
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id UUID PRIMARY KEY,
                customer_id INT NOT NULL,
                amount NUMERIC(12, 2) NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox_events (
                id BIGSERIAL PRIMARY KEY,
                event_id UUID NOT NULL UNIQUE,
                aggregate_type TEXT NOT NULL,
                aggregate_id UUID NOT NULL,
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                published_at TIMESTAMPTZ
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
            ON outbox_events (published_at, id);
            """
        )
        conn.commit()


class CreateOrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    amount: float = Field(gt=0)


def create_api() -> FastAPI:
    app = FastAPI(title="Lab 7 - Transactional Outbox")

    @app.on_event("startup")
    def startup():
        init_schema()

    @app.get("/health")
    def health():
        return {"status": "ok", "role": "api"}

    @app.post("/orders")
    def create_order(body: CreateOrderRequest):
        order_id = str(uuid4())
        event_id = str(uuid4())
        payload = {
            "event_id": event_id,
            "event_type": "OrderCreated",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "order_id": order_id,
            "customer_id": body.customer_id,
            "amount": body.amount,
            "status": "NEW",
        }

        try:
            with db_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (id, customer_id, amount, status)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (order_id, body.customer_id, body.amount, "NEW"),
                )
                cur.execute(
                    """
                    INSERT INTO outbox_events (
                        event_id, aggregate_type, aggregate_id, event_type, payload
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb);
                    """,
                    (
                        event_id,
                        "order",
                        order_id,
                        "OrderCreated",
                        json.dumps(payload),
                    ),
                )
                conn.commit()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

        return {"order_id": order_id, "event_id": event_id, "status": "NEW"}

    @app.get("/orders")
    def list_orders():
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, customer_id, amount::float, status, created_at
                FROM orders
                ORDER BY created_at DESC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "customer_id": row[1],
                "amount": row[2],
                "status": row[3],
                "created_at": row[4].isoformat(),
            }
            for row in rows
        ]

    @app.get("/outbox")
    def list_outbox():
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, event_id::text, event_type, created_at, published_at
                FROM outbox_events
                ORDER BY id DESC
                LIMIT 50;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "event_id": row[1],
                "event_type": row[2],
                "created_at": row[3].isoformat(),
                "published_at": row[4].isoformat() if row[4] else None,
            }
            for row in rows
        ]

    return app


def run_relay():
    init_schema()
    print("[relay] started")

    while True:
        try:
            with db_conn() as conn, conn.cursor() as cur, rabbit_channel() as channel:
                cur.execute(
                    """
                    SELECT id, event_id::text, event_type, payload::text
                    FROM outbox_events
                    WHERE published_at IS NULL
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 20;
                    """
                )
                rows = cur.fetchall()

                if not rows:
                    conn.commit()
                    time.sleep(1.0)
                    continue

                for row in rows:
                    outbox_id = row[0]
                    event_id = row[1]
                    event_type = row[2]
                    payload = row[3]

                    channel.basic_publish(
                        exchange="",
                        routing_key=OUTBOX_QUEUE,
                        body=payload.encode("utf-8"),
                        properties=pika.BasicProperties(
                            content_type="application/json",
                            delivery_mode=2,
                            message_id=event_id,
                            type=event_type,
                        ),
                    )

                    cur.execute(
                        """
                        UPDATE outbox_events
                        SET published_at = NOW()
                        WHERE id = %s;
                        """,
                        (outbox_id,),
                    )

                conn.commit()
                print(f"[relay] published {len(rows)} event(s)")
        except Exception as exc:
            print(f"[relay] error: {exc}")
            time.sleep(2.0)


def run_consumer():
    print("[consumer] started")
    while True:
        try:
            with rabbit_channel() as channel:
                channel.basic_qos(prefetch_count=10)

                def on_message(ch, method, properties, body):
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        print(
                            f"[consumer] got event "
                            f"message_id={properties.message_id} payload={payload}"
                        )
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception as exc:
                        print(f"[consumer] parse error: {exc}")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

                channel.basic_consume(queue=OUTBOX_QUEUE, on_message_callback=on_message)
                channel.start_consuming()
        except Exception as exc:
            print(f"[consumer] error: {exc}")
            time.sleep(2.0)


if APP_ROLE == "api":
    import uvicorn

    app = create_api()
    uvicorn.run(app, host="0.0.0.0", port=8080)
elif APP_ROLE == "relay":
    run_relay()
elif APP_ROLE == "consumer":
    run_consumer()
else:
    raise RuntimeError(f"Unknown APP_ROLE={APP_ROLE}")
