import json
import os
import time
from typing import Any

from kafka import KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError


def env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def wait_for_kafka(bootstrap_servers: str, attempts: int = 30, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers, client_id="lab5-admin")
            admin.list_topics()
            admin.close()
            print(f"Kafka is ready: {bootstrap_servers}")
            return
        except Exception as error:
            if attempt == attempts:
                raise RuntimeError(f"Kafka is not ready after {attempts} attempts: {error}") from error
            print(f"Waiting for Kafka ({attempt}/{attempts})...")
            time.sleep(delay_seconds)


def ensure_topic(
    bootstrap_servers: str,
    topic_name: str,
    partitions: int,
    replication_factor: int,
) -> None:
    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers, client_id="lab5-admin")
    try:
        topic = NewTopic(
            name=topic_name,
            num_partitions=partitions,
            replication_factor=replication_factor,
        )
        admin.create_topics([topic], validate_only=False)
        print(
            f"Topic created: {topic_name} "
            f"(partitions={partitions}, replication_factor={replication_factor})"
        )
    except TopicAlreadyExistsError:
        print(f"Topic already exists: {topic_name}")
    finally:
        admin.close()


def serialize_transaction(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def deserialize_transaction(raw_bytes: bytes) -> dict[str, Any]:
    return json.loads(raw_bytes.decode("utf-8"))
