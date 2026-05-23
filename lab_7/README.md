# Лабораторная работа 7

## Transactional Outbox

В этой лабораторной работе реализован паттерн **Transactional Outbox**. Он нужен, когда сервис должен одновременно изменить данные в базе и отправить событие в брокер сообщений.

Главная проблема: если сначала записать заказ в базу, а потом отправить событие в RabbitMQ, между этими действиями может произойти сбой. Тогда заказ уже есть, а события нет. Transactional Outbox решает это так: событие сначала записывается в таблицу `outbox_events` в той же SQL-транзакции, что и заказ, а отдельный relay-процесс отправляет его в брокер позже.

## Что запускается

- `lab7-postgres` - PostgreSQL, порт `5438`.
- `lab7-rabbitmq` - RabbitMQ, AMQP-порт `5672`, web UI на `localhost:15672`.
- `lab7-api` - FastAPI-сервис, порт `8087`.
- `lab7-outbox-relay` - процесс, который читает `outbox_events` и публикует сообщения в RabbitMQ.
- `lab7-consumer` - consumer, который читает события из очереди.

RabbitMQ UI:

```text
http://localhost:15672
```

Логин и пароль:

```text
guest / guest
```

## Как это работает

1. Клиент отправляет `POST /orders`.
2. API открывает SQL-транзакцию.
3. В таблицу `orders` записывается заказ.
4. В таблицу `outbox_events` записывается событие `OrderCreated`.
5. Транзакция фиксируется.
6. `outbox-relay` находит неопубликованные события.
7. Relay отправляет событие в RabbitMQ queue `orders.events`.
8. После успешной отправки relay заполняет поле `published_at`.
9. `consumer` читает событие из RabbitMQ и пишет его в логи.

Если транзакция откатилась, не будет ни заказа, ни события. Если транзакция сохранилась, событие останется в outbox и будет отправлено позже.

## Запуск

Из папки `lab_7`:

```bash
docker compose up --build
```

## Проверка

Создать заказ:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8087/orders" `
  -ContentType "application/json" `
  -Body '{"customer_id": 101, "amount": 1250.50}'
```

Посмотреть список заказов:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8087/orders"
```

Посмотреть outbox:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8087/outbox"
```

Сначала у события может быть:

```text
published_at = null
```

После работы `outbox-relay` поле `published_at` заполнится.

Посмотреть публикацию и получение события:

```bash
docker compose logs -f outbox-relay consumer
```

## Полезные эндпоинты

- `GET /health` - проверка API.
- `POST /orders` - создать заказ и outbox-событие.
- `GET /orders` - список заказов.
- `GET /outbox` - список событий в outbox.

## Почему это надежнее прямой отправки

При прямой отправке в RabbitMQ возможны частичные состояния:

- заказ создан, но событие не отправилось;
- событие отправилось, но запись заказа откатилась;
- сервис упал между базой и брокером.

Transactional Outbox убирает эту проблему: заказ и запись события сохраняются одной транзакцией. Отправка в брокер становится отдельным надежно повторяемым шагом.

## Остановка

```bash
docker compose down
```

Удалить данные:

```bash
docker compose down -v
```

## Итог

Лабораторная показывает надежный способ публиковать события из сервиса, который хранит состояние в SQL-базе. Это один из стандартных паттернов для микросервисов и событийной архитектуры.
