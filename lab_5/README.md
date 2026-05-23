# Лабораторная работа 5

## Kafka: topic, partitions, producer и consumer group

Эта лабораторная работа показывает обмен сообщениями через Kafka. Producer отправляет JSON-сообщения о транзакциях в topic `transactions`, а два consumer-а читают их в одной consumer group.

## Что запускается

- `lab5-zookeeper` - Zookeeper для Kafka.
- `lab5-kafka` - Kafka broker.
- `lab5-producer` - отправляет сообщения.
- `lab5-consumer-1` - первый consumer.
- `lab5-consumer-2` - второй consumer.

## Что делает producer

Producer создает topic `transactions` с параметрами:

- `3` partition;
- `replication_factor=1`.

Затем он отправляет JSON-сообщения с полями:

```json
{
  "user_id": 101,
  "amount": 500,
  "type": "incoming"
}
```

Ключ сообщения - `user_id`. Это важно: Kafka отправляет сообщения с одинаковым ключом в одну и ту же partition. Поэтому события одного пользователя сохраняют порядок внутри своей partition.

## Что делают consumers

Два consumer-а работают в одной группе:

```text
transaction-group
```

Kafka распределяет partitions между consumer-ами внутри группы. Одно сообщение обрабатывается только одним consumer-ом этой группы, поэтому дублирования обработки внутри группы нет.

## Состав файлов

- `docker-compose.yml` - Kafka, Zookeeper, producer и consumers.
- `app/common.py` - общие настройки и сериализация.
- `app/producer.py` - создание topic и отправка сообщений.
- `app/consumer.py` - чтение сообщений.
- `app/Dockerfile` и `app/requirements.txt` - сборка Python-контейнера.

## Запуск

Из папки `lab_5`:

```bash
docker compose up --build
```

## Что смотреть в логах

Логи producer-а:

```bash
docker compose logs -f producer
```

В них видно, в какую partition ушло каждое сообщение. Для одинакового `user_id` partition должна совпадать.

Логи consumer-ов:

```bash
docker compose logs -f consumer-1 consumer-2
```

В них видно, что сообщения распределяются между двумя consumer-ами. Каждый consumer получает только часть partitions.

Можно смотреть все сразу:

```bash
docker compose logs -f producer consumer-1 consumer-2
```

## Что должно получиться

- topic `transactions` создается автоматически;
- сообщения отправляются в Kafka в JSON-формате;
- одинаковые `user_id` попадают в одну partition;
- два consumer-а делят partitions между собой;
- сообщение внутри одной consumer group обрабатывается одним consumer-ом.

## Остановка

```bash
docker compose down
```

Остановить и удалить данные Kafka:

```bash
docker compose down -v
```

## Итог

Лабораторная показывает, зачем в Kafka нужны partitions, как ключ сообщения влияет на распределение, и как consumer group позволяет параллельно обрабатывать поток без дублирования внутри группы.
