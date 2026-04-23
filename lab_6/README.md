# Лабораторная работа 6

Тема: Паттерны проектирования в Web Design (архитектурные и инфраструктурные паттерны).

Спроектирована и реализована система обработки платежных заказов (маркетплейс-сценарий) с применением требуемых паттернов.

## Состав решения

- `docker-compose.yml`
- `app/Dockerfile`
- `app/requirements.txt`
- `app/app.py`

## Запуск

```bash
docker compose up --build
```

API gateway: `http://localhost:8080`

## 1. Архитектура

### Трехзвенная архитектура

- Client: HTTP-клиент (curl/Postman/браузер) обращается только в `gateway`.
- Backend: `gateway`, `order`, `payment`, `worker`, `notifier`, `discovery`.
- Database: `postgres` (command model), `redis` (read model/cache + stream + pub/sub).

### Тип клиента

- Тонкий клиент (thin client): вся бизнес-логика в backend.

## 2. Взаимодействие сервисов

Используются:

- Pub/Sub: Redis channel `events`, подписчик `notifier`.
- Service Discovery: сервис `discovery` (`/register`, `/resolve/{service}`).
- Heartbeat: `gateway`, `order`, `payment` шлют heartbeat каждые 5 секунд в `discovery`.

## 3. Работа с данными

### CQRS

- Command side: таблица `orders` в Postgres.
- Query side: Redis `order:view:{id}` (версия, ETag, cache tag).

### Обработка данных (MapReduce)

Эндпоинт `GET /analytics/daily` в `order`:

- Map: `order -> (day, paid_amount)`
- Reduce: суммирование по `day`

## 4. Надежность

Реализовано:

- Retries + Backoff: worker повторяет оплату до 5 раз (`2^attempt`, максимум 16 сек).
- Idempotency: `Idempotency-Key` при создании заказа (`idempotency_key` unique в БД).
- Circuit Breaker: в worker для вызовов `payment` (closed/open/half-open).
- Backpressure: ограничение глубины очереди (`BACKPRESSURE_LIMIT`), при перегрузке `429`.

Обработка ошибок:

- Fallback: при открытом circuit breaker заказ уходит в `REVIEW`.
- Graceful Degradation: если read-model/кэш недоступен, чтение идет из Postgres (`degraded: true`).

## 5. Кэширование

- Версионирование кэша: поле `version` в Redis-проекции.
- Тегирование кэша: `cache_tag = user:{user_id}`, набор ключей `cache:tag:*`.
- ETag/If-None-Match: для чтения заказа (условные GET).

## 6. Асинхронность

- Отложенные задачи: команды обработки заказа кладутся в Redis Stream `orders:commands`.
- Очередь сообщений: worker читает stream через consumer group `order-workers`.

## 7. Получение данных

Реализованы подходы:

- Polling: `GET /api/orders/{id}/status`
- Long Polling: `GET /api/orders/{id}/status/long-poll?current_status=PENDING&timeout_seconds=20`
- Streaming (SSE): `GET /api/orders/{id}/status/stream`

## 8. Деплой (стратегии)

Рекомендуемые стратегии для этой архитектуры:

- Rolling Release: постепенное обновление контейнеров `gateway/order/payment` без полного даунтайма.
- Blue/Green: две одинаковые среды (Blue и Green), переключение трафика после smoke-check.
- Canary Release: направлять 5-10% трафика на новую версию `payment`, затем расширять долю.

## Проверка (минимальный сценарий)

1. Создать заказ:

```bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-001" \
  -d '{"user_id": 101, "amount": 1200.50}'
```

2. Polling статуса:

```bash
curl http://localhost:8080/api/orders/<ORDER_ID>/status
```

3. Long Polling:

```bash
curl "http://localhost:8080/api/orders/<ORDER_ID>/status/long-poll?current_status=PENDING&timeout_seconds=20"
```

4. Streaming (SSE):

```bash
curl -N http://localhost:8080/api/orders/<ORDER_ID>/status/stream
```

5. Проверка сервис-дискавери и heartbeat:

```bash
curl http://localhost:8500/services
```

6. Проверка событий Pub/Sub:

```bash
docker compose logs -f notifier
```

## Краткие ответы по заданию

- Какие паттерны использованы и зачем:
  - CQRS для разделения write/read нагрузки,
  - Pub/Sub и queue для слабой связанности,
  - Service Discovery + heartbeat для динамического обнаружения живых инстансов,
  - Retry/Backoff + Circuit Breaker + Fallback для устойчивости к временным сбоям,
  - Backpressure для защиты от перегрузки,
  - Cache version/tag + ETag для эффективного чтения.

- Как обеспечена отказоустойчивость:
  - повторные попытки с экспоненциальной задержкой,
  - автоматическое размыкание circuit breaker,
  - деградация чтения с Redis на Postgres,
  - асинхронная обработка через очередь при пиковых нагрузках.

- Как масштабируется система:
  - горизонтально масштабируются `gateway/order/payment/worker`;
  - через discovery можно добавить инстансы без изменения клиентского кода;
  - queue + worker pool позволяет наращивать throughput фоновой обработки.
