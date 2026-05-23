# Лабораторная работа 6

## Архитектурные и инфраструктурные паттерны web-систем

В этой лабораторной работе реализован небольшой marketplace-сценарий: пользователь создает заказ, заказ попадает в очередь, worker пытается провести оплату, а статус заказа можно читать разными способами.

Цель - показать, как в одной системе применяются gateway, service discovery, CQRS, очередь, retries, circuit breaker, idempotency, backpressure, cache и разные способы получения статуса.

## Что запускается

- `postgres` - основная база заказов.
- `redis` - read model, cache, stream и pub/sub.
- `discovery` - сервис регистрации и поиска сервисов, доступен на `localhost:8560`.
- `order` - сервис заказов, доступен на `localhost:8061`.
- `payment` - сервис оплаты, доступен на `localhost:8062`.
- `gateway` - основная точка входа API, доступна на `localhost:8060`.
- `worker` - фоновый обработчик заказов.
- `notifier` - подписчик на события Redis Pub/Sub.

## Как работает сценарий

1. Клиент отправляет запрос на gateway: `POST /api/orders`.
2. Gateway находит сервис `order` через discovery.
3. Order-сервис создает заказ в PostgreSQL.
4. Для чтения создается проекция заказа в Redis.
5. Команда обработки заказа кладется в Redis Stream `orders:commands`.
6. Worker читает команду из stream и вызывает `payment`.
7. Если оплата успешна, заказ получает статус `PAID`.
8. Если есть временные ошибки, worker повторяет попытки с backoff.
9. Если circuit breaker открыт, заказ переводится в `REVIEW`.
10. Notifier получает события через Redis Pub/Sub и пишет их в логи.

## Паттерны в работе

- **API Gateway** - клиент обращается к одному сервису `gateway`.
- **Service Discovery** - сервисы регистрируются и отправляют heartbeat.
- **CQRS** - запись хранится в PostgreSQL, read model хранится в Redis.
- **Queue / Stream** - обработка заказа выполняется асинхронно через Redis Stream.
- **Pub/Sub** - события публикуются в Redis channel `events`.
- **Idempotency** - повторный запрос с тем же `Idempotency-Key` не создает новый заказ.
- **Retries + Backoff** - worker повторяет оплату с увеличением задержки.
- **Circuit Breaker** - при серии ошибок вызовы к payment временно блокируются.
- **Fallback** - при проблемах заказ уходит в статус `REVIEW`.
- **Graceful Degradation** - если Redis недоступен, чтение может идти из PostgreSQL.
- **Backpressure** - при слишком большой очереди сервис возвращает `429`.
- **ETag** - чтение заказа поддерживает условные GET-запросы.

## Запуск

Из папки `lab_6`:

```bash
docker compose up --build
```

Основной адрес API:

```text
http://localhost:8060
```

## Минимальная проверка

Создать заказ:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8060/api/orders" `
  -ContentType "application/json" `
  -Headers @{ "Idempotency-Key" = "demo-001" } `
  -Body '{"user_id": 101, "amount": 1200.50}'
```

В ответе будет `order_id`. Его нужно подставить в следующие запросы.

Проверить заказ:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8060/api/orders/<ORDER_ID>"
```

Проверить статус через polling:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8060/api/orders/<ORDER_ID>/status"
```

Проверить long polling:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8060/api/orders/<ORDER_ID>/status/long-poll?current_status=PENDING&timeout_seconds=20"
```

Проверить SSE streaming:

```powershell
Invoke-WebRequest -Uri "http://localhost:8060/api/orders/<ORDER_ID>/status/stream"
```

Проверить service discovery:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8560/services"
```

Посмотреть события:

```bash
docker compose logs -f notifier
```

## Полезные эндпоинты

Gateway:

- `POST /api/orders` - создать заказ;
- `GET /api/orders/{order_id}` - получить заказ;
- `GET /api/orders/{order_id}/status` - обычный polling;
- `GET /api/orders/{order_id}/status/long-poll` - long polling;
- `GET /api/orders/{order_id}/status/stream` - SSE stream.

Discovery:

- `GET /services` - список зарегистрированных сервисов;
- `GET /resolve/{service}` - адрес конкретного сервиса.

Order:

- `GET /analytics/daily` - простая daily-аналитика по заказам.

## Остановка

```bash
docker compose down
```

Удалить данные:

```bash
docker compose down -v
```

## Итог

Лабораторная показывает, как строится более реалистичная web-система: запросы проходят через gateway, сервисы обнаруживают друг друга через discovery, запись и чтение разделены, тяжелая обработка уходит в очередь, а сбои обрабатываются контролируемо.
