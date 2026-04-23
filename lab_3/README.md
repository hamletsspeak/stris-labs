# Лабораторная работа 3

Тема: распределенное хранение данных (простая репликация в памяти).

## Что реализовано

3 узла в `docker-compose`:
- `master` (Node A) на `localhost:8080`
- `replica1` (Node B) на `localhost:8081`
- `replica2` (Node C) на `localhost:8082`

Поведение:
- `master` принимает запись (`POST /data`) и рассылает ее на реплики (`POST /replica/data`).
- Все данные хранятся в памяти процесса каждого узла.
- `replica` хранит только пришедшие от `master` данные.

## Эндпоинты

### Master
- `POST /data`
  - Запись данных на master и попытка репликации на все replica.
  - Вход: JSON `{ "key": "name", "value": "Alice" }`
  - Также поддерживаются query-параметры: `?key=name&value=Alice`
- `GET /data/<key>`
  - Получение значения по ключу.

### Replica
- `POST /replica/data`
  - Получение реплицируемых данных от master.
  - Вход: JSON `{ "key": "name", "value": "Alice" }`
- `GET /data/<key>`
  - Получение значения по ключу.

### Вспомогательный
- `GET /health` на любом узле

## Запуск
```bash
docker compose up --build -d
```

Проверка здоровья:
```bash
curl http://localhost:8080/health
curl http://localhost:8081/health
curl http://localhost:8082/health
```

## Задание 1: простая репликация

1. Записать данные через master:
```bash
curl -X POST "http://localhost:8080/data?key=name&value=Alice"
```

2. Прочитать на master и репликах:
```bash
curl http://localhost:8080/data/name
curl http://localhost:8081/data/name
curl http://localhost:8082/data/name
```

Ожидаемо: значение `Alice` есть на всех трех узлах.

## Задание 2: имитация сбоя

1. Отключить одну replica:
```bash
docker compose stop replica1
```

2. Выполнить запись через master, пока `replica1` отключена:
```bash
curl -X POST "http://localhost:8080/data?key=city&value=Moscow"
```

3. Проверить данные:
```bash
curl http://localhost:8080/data/city
curl http://localhost:8082/data/city
```

4. Включить `replica1` обратно:
```bash
docker compose start replica1
```

5. Сравнить состояние после восстановления:
```bash
curl http://localhost:8081/data/city
curl http://localhost:8082/data/city
curl http://localhost:8080/data/city
```

Ожидаемо:
- `master` и активная во время записи `replica2` содержат ключ `city`.
- восстановленная `replica1` может не содержать `city` (404), потому что пропустила запись во время простоя.
- так как данные в памяти, после `stop/start` у `replica1` также теряются ранее полученные ключи (например, `name`), пока они снова не будут реплицированы.
- это демонстрирует возможное расхождение данных между узлами при сбое.

## Логи
```bash
docker compose logs -f
```

## Остановка
```bash
docker compose down
```
