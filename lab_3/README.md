# Лабораторная работа 3

## Простая репликация данных

В этой лабораторной работе реализована минимальная модель распределенного key-value хранилища. Есть один master-узел и две replica-ноды. Данные хранятся в памяти процесса, без базы данных.

Цель работы - показать, как master принимает запись, рассылает ее репликам и что происходит, если одна из реплик была недоступна.

## Что запускается

- `lab3-master` - master-узел, доступен на `localhost:8080`.
- `lab3-replica1` - первая реплика, доступна на `localhost:8081`.
- `lab3-replica2` - вторая реплика, доступна на `localhost:8082`.

Все три контейнера запускают один и тот же Flask-код. Роль узла задается переменной окружения `NODE_ROLE`.

## Как работает запись

Клиент отправляет запись на master:

```http
POST /data
```

Master сохраняет значение у себя и отправляет его на каждую реплику через внутренний эндпоинт:

```http
POST /replica/data
```

Если реплика недоступна, master продолжает работу, но эта реплика пропускает запись. Автоматической догрузки пропущенных данных здесь нет.

## Эндпоинты

### `GET /health`

Проверяет состояние любого узла.

### `POST /data`

Записывает данные через master.

Можно передать JSON:

```json
{
  "key": "name",
  "value": "Alice"
}
```

Или query-параметры:

```text
/data?key=name&value=Alice
```

### `POST /replica/data`

Внутренний эндпоинт реплики. Master вызывает его при репликации.

### `GET /data/<key>`

Возвращает значение по ключу на конкретном узле.

## Запуск

Из папки `lab_3`:

```bash
docker compose up --build -d
```

## Проверка health

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/health"
Invoke-RestMethod -Method Get -Uri "http://localhost:8081/health"
Invoke-RestMethod -Method Get -Uri "http://localhost:8082/health"
```

## Сценарий 1: обычная репликация

Запишите данные через master:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/data?key=name&value=Alice"
```

Проверьте значение на всех узлах:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data/name"
Invoke-RestMethod -Method Get -Uri "http://localhost:8081/data/name"
Invoke-RestMethod -Method Get -Uri "http://localhost:8082/data/name"
```

Ожидаемый результат: значение `Alice` есть на master и на обеих репликах.

## Сценарий 2: сбой реплики

Остановите одну реплику:

```bash
docker compose stop replica1
```

Запишите новое значение через master:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/data?key=city&value=Moscow"
```

Проверьте master и работающую реплику:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data/city"
Invoke-RestMethod -Method Get -Uri "http://localhost:8082/data/city"
```

Верните `replica1`:

```bash
docker compose start replica1
```

Проверьте ее состояние:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8081/data/city"
```

Ожидаемый результат: `replica1` может не знать про `city`, потому что во время записи была выключена. Так демонстрируется рассинхронизация данных.

## Логи

```bash
docker compose logs -f
```

## Остановка

```bash
docker compose down
```

## Итог

Лабораторная показывает базовую идею репликации и важную проблему распределенных систем: если узел был недоступен, он может отстать от остальных и потребовать отдельного механизма восстановления.
