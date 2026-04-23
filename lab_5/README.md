# Лабораторная работа 5

Тема: Kafka (topic, partitioning, producer/consumer group, JSON сериализация/десериализация).

## Что реализовано

- `zookeeper` + `kafka` в `docker-compose`.
- Topic `transactions` создается автоматически producer-ом:
  - `3` партиции,
  - `replication_factor=1`.
- Формат сообщений: JSON.
- Поля сообщения: `user_id`, `amount`, `type` (`incoming`/`outgoing`).
- Ключ сообщения: `user_id` (строка).  
  Это гарантирует, что одинаковый `user_id` всегда попадает в одну и ту же партицию.
- 2 consumer-а в одной `consumer group`: `transaction-group`.

## Состав

- `docker-compose.yml`
- `app/Dockerfile`
- `app/requirements.txt`
- `app/common.py`
- `app/producer.py`
- `app/consumer.py`

## Запуск

```bash
docker compose up --build
```

## Что проверить в логах

1. В логах `producer` видно, в какую партицию ушло каждое сообщение:
```text
user_id=101 ... -> partition=...
user_id=101 ... -> partition=...
```
Для одного и того же `user_id` партиция должна совпадать.

2. Для других `user_id` партиции могут отличаться:
```text
user_id=202 ... -> partition=...
user_id=303 ... -> partition=...
```

3. В логах `consumer-1` и `consumer-2` видно чтение из топика `transactions` в группе `transaction-group`:
- Kafka сама распределяет партиции между consumer-ами внутри одной группы.
- Сообщение читается только одним consumer-ом группы (без дублей внутри группы).

## Полезные команды

Показать логи:
```bash
docker compose logs -f producer consumer-1 consumer-2
```

Остановить:
```bash
docker compose down
```

Остановить и удалить данные:
```bash
docker compose down -v
```
