# Лабораторная работа 7

Тема: реализация паттерна **Transactional Outbox**.

## Что реализовано

- `api` сервис (FastAPI), который создаёт заказ.
- В одной SQL-транзакции выполняются:
  - запись в `orders`,
  - запись события в `outbox_events`.
- `outbox-relay` периодически читает неотправленные записи из `outbox_events`, публикует их в RabbitMQ и помечает `published_at`.
- `consumer` читает события из очереди `orders.events` и выводит их в лог.

## Состав

- `docker-compose.yml`
- `app/Dockerfile`
- `app/requirements.txt`
- `app/main.py`

## Запуск

```bash
cd lab_7
docker compose up --build
```

Сервисы:

- API: `http://localhost:8087`
- RabbitMQ UI: `http://localhost:15672` (`guest` / `guest`)
- Postgres: `localhost:5438` (`demo` / `demo`)

## Проверка

1. Создать заказ:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8087/orders" `
  -ContentType "application/json" `
  -Body '{"customer_id": 101, "amount": 1250.50}'
```

2. Проверить список заказов:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8087/orders"
```

3. Проверить outbox:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8087/outbox"
```

Вначале у записи может быть `published_at = null`, после работы `outbox-relay` поле заполняется.

4. Проверить доставку события:

```bash
docker compose logs -f consumer outbox-relay
```

В логах будет видно публикацию relay и получение события consumer-ом.

## Почему это Transactional Outbox

Событие не отправляется напрямую из API в брокер.
API пишет событие в таблицу `outbox_events` в **той же транзакции**, где создаётся заказ.

Это гарантирует:

- если транзакция откатилась, нет ни заказа, ни события;
- если транзакция зафиксирована, событие точно останется в outbox и будет отправлено relay-процессом позже.
