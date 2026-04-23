# Лабораторная работа 4

Тема: проектирование БД кошелька доходов/расходов с партиционированием, шардированием и репликацией.

## Состав решения
- `docker-compose.yml`
- `app/Dockerfile`
- `app/requirements.txt`
- `app/app.py`

Запуск:
```bash
docker compose up --build
```

Контейнер `app`:
- поднимает схему на каждом primary-шарде,
- создает партиционированную таблицу транзакций,
- раскладывает пользователей по шардам,
- пишет данные в `primary`,
- читает отчеты из `replica`.

## Задание 1. Проектирование базы данных

Сущности:
- `users(id, full_name, email, created_at)`
- `accounts(id, user_id, account_name, balance)`
- `categories(id, user_id, category_name, kind)`
- `transactions(transaction_id, user_id, account_id, category_id, amount, note, transaction_date, created_at)`
- `daily_user_aggregates(user_id, day, total_income, total_expense)`

Связи:
- `users 1:N accounts`
- `users 1:N categories`
- `users 1:N transactions`
- `accounts 1:N transactions`
- `categories 1:N transactions`

Краткая ER-диаграмма:
```text
users (1) --- (N) accounts
users (1) --- (N) categories
users (1) --- (N) transactions
accounts (1) --- (N) transactions
categories (1) --- (N) transactions
users (1) --- (N) daily_user_aggregates
```

## Задание 2. Партиционирование

Выбран объект: `transactions` (самый большой рост данных).

Тип: `RANGE PARTITION` по `transaction_date` (месячные разделы).

Критерий: дата транзакции.

Структура:
- `transactions` — родительская таблица
- `transactions_YYYY_MM` — месячные партиции
- `transactions_default` — fallback для дат вне явных диапазонов
- индекс: `idx_transactions_user_date (user_id, transaction_date)`

Почему так:
- отчеты за месяц/квартал сканируют только нужные партиции;
- проще архивировать старые периоды (detach/drop);
- сокращается I/O при аналитических запросах по времени.

## Задание 3. Шардирование

Способ: горизонтальное шардирование по пользователю.

Ключ: `user_id`.

Алгоритм распределения:
- `shard_index = user_id % 2`
- `0 -> shard_1`, `1 -> shard_2`

Указано:
- количество шардов: `2` (по ТЗ можно масштабировать до `N`)
- как определяется нужный шард: вычисление остатка от деления `user_id`
- где хранятся данные пользователя: все его сущности (`users/accounts/categories/transactions/aggregates`) в одном шарде

Плюсы:
- локальные транзакции по одному пользователю,
- простой и быстрый роутинг,
- равномерная нагрузка для последовательных id.

## Задание 4. Репликация

Структура:
- для каждого шарда есть `primary` и `replica`:
  - `shard1-primary -> shard1-replica`
  - `shard2-primary -> shard2-replica`

Маршрутизация:
- записи (`INSERT/UPDATE/DELETE`) идут в `primary`
- чтение отчетов идет из `replica`

Поведение при сбоях:
- если падает `replica`, запись продолжается в `primary`, но часть read-only нагрузки теряется;
- если падает `primary`, запись в этот шард останавливается до failover/promote;
- возможна задержка репликации (eventual consistency), поэтому чтение сразу после записи может временно не видеть данные.

## Задание 5. Архитектура системы

```text
[Client/API]
   |
   v
[Router by user_id % shard_count]
   |------------------------------|
   v                              v
[Shard 1 Primary] ----replicate-> [Shard 1 Replica]
[Shard 2 Primary] ----replicate-> [Shard 2 Replica]
```

Правила:
- router определяет шард по `user_id`;
- write-path: только `primary`;
- read-path: `replica`;
- партиционирование применяется внутри каждого шарда для `transactions`.

## Задание 6. Анализ

1. Почему выбран этот способ шардирования:
- ключ `user_id` естественный для домена кошелька;
- операции пользователя чаще всего локальны и не требуют cross-shard join.

2. Преимущества партиционирования:
- ускорение time-range запросов;
- управляемость жизненного цикла данных;
- снижение объема сканируемых страниц.

3. Возможные проблемы:
- hot-shard при неравномерном распределении ключей;
- сложные межшардовые запросы и транзакции;
- лаг репликации и чтение устаревших данных.

4. Масштабирование:
- добавление новых шардов (`N -> N+1`) с ребалансировкой;
- балансировка read-запросов по нескольким replica;
- выделение отдельного аналитического контура.

## Полезные команды

Показать результат выполнения приложения:
```bash
docker compose logs app
```

Остановить:
```bash
docker compose down
```

Остановить и очистить данные:
```bash
docker compose down -v
```
