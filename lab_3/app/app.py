import os
from typing import Any

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

NODE_ROLE = os.getenv("NODE_ROLE", "replica").strip().lower()
NODE_NAME = os.getenv("NODE_NAME", "node")
PORT = int(os.getenv("PORT", "8080"))
REPLICA_URLS = [
    url.strip().rstrip("/")
    for url in os.getenv("REPLICA_URLS", "").split(",")
    if url.strip()
]

storage: dict[str, Any] = {}


def extract_payload() -> tuple[str, Any]:
    body = request.get_json(silent=True) or {}
    key = body.get("key") or request.args.get("key")
    value = body.get("value")

    # Support value from query-string for easier manual testing.
    if value is None and "value" in request.args:
        value = request.args.get("value")

    if key is None or value is None:
        raise ValueError("Both 'key' and 'value' are required")

    return str(key), value


@app.get("/health")
def health() -> Any:
    return jsonify(
        {
            "status": "ok",
            "node": NODE_NAME,
            "role": NODE_ROLE,
            "keys": len(storage),
        }
    )


@app.post("/data")
def write_data_master() -> Any:
    if NODE_ROLE != "master":
        return jsonify({"error": "Endpoint /data for write is available only on master"}), 405

    try:
        key, value = extract_payload()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    storage[key] = value
    replication_report = []

    for replica_url in REPLICA_URLS:
        target = f"{replica_url}/replica/data"
        try:
            response = requests.post(
                target,
                json={"key": key, "value": value},
                timeout=2,
            )
            replication_report.append(
                {
                    "replica": replica_url,
                    "status": "ok" if response.ok else "failed",
                    "http_status": response.status_code,
                }
            )
        except requests.RequestException as exc:
            replication_report.append(
                {
                    "replica": replica_url,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return jsonify(
        {
            "node": NODE_NAME,
            "role": NODE_ROLE,
            "stored": {"key": key, "value": value},
            "replication": replication_report,
        }
    )


@app.post("/replica/data")
def write_data_replica() -> Any:
    if NODE_ROLE != "replica":
        return jsonify({"error": "Endpoint /replica/data is available only on replica"}), 405

    body = request.get_json(silent=True) or {}
    key = body.get("key")
    value = body.get("value")

    if key is None or value is None:
        return jsonify({"error": "JSON with 'key' and 'value' is required"}), 400

    storage[str(key)] = value

    return jsonify(
        {
            "node": NODE_NAME,
            "role": NODE_ROLE,
            "stored": {"key": str(key), "value": value},
        }
    )


@app.get("/data/<key>")
def read_data(key: str) -> Any:
    if key not in storage:
        return (
            jsonify(
                {
                    "node": NODE_NAME,
                    "role": NODE_ROLE,
                    "key": key,
                    "found": False,
                }
            ),
            404,
        )

    return jsonify(
        {
            "node": NODE_NAME,
            "role": NODE_ROLE,
            "key": key,
            "value": storage[key],
            "found": True,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
