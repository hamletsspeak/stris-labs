import json
import os
import random
import string
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from redis import Redis
from redis.exceptions import RedisError

app = Flask(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "service-unknown")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def random_value() -> str:
    suffix = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"Random data {suffix}"


@app.get("/info")
def info():
    return jsonify({"service": SERVICE_NAME, "time": now_iso()})


@app.get("/data")
def data():
    raw_id = request.args.get("id")
    if raw_id is None:
        return jsonify({"error": "Query parameter id is required"}), 400

    try:
        item_id = int(raw_id)
    except ValueError:
        return jsonify({"error": "Query parameter id must be an integer"}), 400

    cache_key = f"data:{item_id}"

    try:
        cached = redis_client.get(cache_key)
    except RedisError:
        cached = None

    if cached:
        return jsonify({"id": item_id, "value": cached, "source": "cache"})

    value = random_value()

    try:
        redis_client.set(cache_key, value)
    except RedisError:
        pass

    return jsonify({"id": item_id, "value": value, "source": "generated"})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": SERVICE_NAME})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
