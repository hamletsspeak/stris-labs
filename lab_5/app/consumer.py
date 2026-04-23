from kafka import KafkaConsumer
from kafka.errors import KafkaError

from common import deserialize_transaction, env, wait_for_kafka


def main() -> None:
    bootstrap = env("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = env("TOPIC_NAME", "transactions")
    group_id = env("GROUP_ID", "transaction-group")
    consumer_name = env("CONSUMER_NAME", "consumer")
    max_messages = int(env("MAX_MESSAGES", "10"))

    print(f"=== LAB 5: {consumer_name} ===")
    wait_for_kafka(bootstrap)

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        key_deserializer=lambda key: key.decode("utf-8") if key else None,
        value_deserializer=deserialize_transaction,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        consumer_timeout_ms=20000,
    )

    print(f"{consumer_name}: subscribed to '{topic}' in group '{group_id}'")
    received = 0

    try:
        for msg in consumer:
            payload = msg.value
            print(
                f"{consumer_name}: partition={msg.partition} offset={msg.offset} "
                f"key={msg.key} user_id={payload.get('user_id')} "
                f"type={payload.get('type')} amount={payload.get('amount')}"
            )
            received += 1
            if received >= max_messages:
                break
    except KafkaError as error:
        print(f"{consumer_name}: kafka error: {error}")
    finally:
        consumer.close()
        print(f"{consumer_name}: finished, received {received} messages")


if __name__ == "__main__":
    main()
