# Лабораторная работа 1

## HTTP-сервис, reverse proxy, балансировка и кэш

В этой лабораторной работе поднимается небольшой HTTP-сервис в нескольких контейнерах. Один и тот же Flask-код запускается в двух экземплярах, перед ними стоит Nginx, а Redis используется для кэширования данных.

Главная идея: показать, как пользователь обращается к одному адресу, а внутри запросы распределяются между несколькими копиями сервиса.

## Что запускается

- `service-1` - первый экземпляр Flask-приложения, доступен напрямую на `localhost:8081`.
- `service-2` - второй экземпляр Flask-приложения, доступен напрямую на `localhost:8082`.
- `lab1-nginx` - Nginx, основная точка входа на `localhost:8080`.
- `lab1-redis` - Redis, общий кэш для обоих экземпляров приложения.

## Как это работает

Пользователь отправляет запрос на `http://localhost:8080`. Этот запрос принимает Nginx и пересылает его в один из backend-контейнеров: `service-1` или `service-2`.

Nginx использует Round Robin: первый запрос уходит в один сервис, следующий - в другой, затем снова в первый. Так нагрузка распределяется между несколькими экземплярами приложения.

Оба сервиса используют общий Redis. Поэтому данные, записанные в кэш одним экземпляром, может прочитать другой экземпляр.

## Эндпоинты

### `GET /info`

Возвращает имя сервиса, который обработал запрос, и текущее время.

```json
{
  "service": "service-1",
  "time": "2026-05-23T07:30:00+00:00"
}
```

Если несколько раз обратиться через Nginx, поле `service` должно чередоваться между `service-1` и `service-2`.

### `GET /data?id=1`

Демонстрирует кэширование.

При первом запросе данных в Redis еще нет. Сервис генерирует случайное значение, сохраняет его в Redis и возвращает:

```json
{
  "id": 1,
  "value": "Random data Ab12Cd34",
  "source": "generated"
}
```

При повторном запросе с тем же `id` значение берется из Redis:

```json
{
  "id": 1,
  "value": "Random data Ab12Cd34",
  "source": "cache"
}
```

Если не передать `id`, сервис вернет ошибку `Query parameter id is required`. Если передать не число, вернется `Query parameter id must be an integer`.

### `GET /health`

Проверяет, что конкретный экземпляр сервиса работает.

```json
{
  "status": "ok",
  "service": "service-1"
}
```

## Запуск

Из папки `lab_1`:

```bash
docker compose up --build -d
```

## Проверка прямого доступа

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8081/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8082/info"
```

В ответах должны быть разные значения `service`: `service-1` и `service-2`.

## Проверка Nginx и Round Robin

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
```

Все запросы идут на один адрес `localhost:8080`, но обрабатываются разными контейнерами.

## Проверка Redis-кэша

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data?id=1"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data?id=1"
```

Ожидаемый результат:

- первый ответ содержит `source: generated`;
- второй ответ содержит `source: cache`;
- поле `value` в обоих ответах одинаковое.

## Остановка

```bash
docker compose down
```

## Итог

Лабораторная показывает базовую схему web-инфраструктуры: несколько экземпляров приложения, единая точка входа через reverse proxy, балансировка нагрузки и общий кэш.
