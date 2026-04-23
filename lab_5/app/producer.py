import time

from kafka import KafkaProducer

from common import ensure_topic, env, serialize_transaction, wait_for_kafka


def build_messages() -> list[dict]:
    return [
        {"user_id": 101, "amount": 1500.0, "type": "incoming"},
        {"user_id": 101, "amount": 250.0, "type": "outgoing"},
        {"user_id": 101, "amount": 600.0, "type": "incoming"},
        {"user_id": 202, "amount": 120.0, "type": "outgoing"},
        {"user_id": 202, "amount": 3000.0, "type": "incoming"},
        {"user_id": 303, "amount": 80.5, "type": "outgoing"},
        {"user_id": 303, "amount": 90.0, "type": "outgoing"},
        {"user_id": 404, "amount": 700.0, "type": "incoming"},
        {"user_id": 505, "amount": 50.0, "type": "outgoing"},
        {"user_id": 505, "amount": 150.0, "type": "incoming"},
    ]


def main() -> None:
    bootstrap = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = env("TOPIC_NAME", "transactions")
    topic_partitions = int(env("TOPIC_PARTITIONS", "3"))
    topic_replicas = int(env("TOPIC_REPLICATION_FACTOR", "1"))

    print("=== LAB 5: producer ===")
    wait_for_kafka(bootstrap)
    ensure_topic(bootstrap, topic, topic_partitions, topic_replicas)

    producer = KafkaProducer(
        bootstrap_servers=bootstrap,
        key_serializer=lambda key: key.encode("utf-8"),
        value_serializer=serialize_transaction,
        acks="all",
    )

    messages = build_messages()
    sent_count = 0

    for index, message in enumerate(messages, start=1):
        user_id = message["user_id"]
        key = str(user_id)
        future = producer.send(topic, key=key, value=message)
        metadata = future.get(timeout=10)
        sent_count += 1
        print(
            f"[{index}/{len(messages)}] user_id={user_id} "
            f"type={message['type']} amount={message['amount']} "
            f"-> partition={metadata.partition}, offset={metadata.offset}"
        )
        time.sleep(0.2)

    producer.flush()
    producer.close()
    print(f"Producer finished, sent {sent_count} messages to topic '{topic}'.")


if __name__ == "__main__":
    main()
