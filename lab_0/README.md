# Лабораторная работа 0

## REST API и OpenAPI

В этой лабораторной работе описан REST API для простой социальной сети. Здесь нет запущенного backend-сервиса: результатом работы является файл `openapi.yaml`, который фиксирует контракт API.

OpenAPI-спецификация нужна для того, чтобы заранее описать, какие запросы поддерживает система, какие параметры она принимает, какие ответы возвращает и как выглядят ошибки.

## Что находится в папке

- `openapi.yaml` - полная спецификация OpenAPI 3.0.3.
- `README.md` - описание лабораторной и примеры основных запросов.

## Что описывает API

Спецификация содержит операции для социальной сети:

- просмотр профиля пользователя;
- добавление друга;
- удаление друга;
- просмотр списка друзей;
- публикация поста.

Базовый адрес API:

```text
http://localhost:8080/api/v1
```

Идентификаторы пользователей и друзей передаются как UUID.

## Основные эндпоинты

### Просмотр профиля пользователя

```http
GET /users/{userId}
```

Возвращает данные пользователя: идентификатор, имя, дату регистрации и другую информацию профиля.

Пример:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1" `
  -Headers @{ Accept = "application/json" }
```

### Добавление друга

```http
POST /users/{userId}/friends
```

Добавляет пользователю нового друга. Идентификатор друга передается в теле запроса.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends" `
  -ContentType "application/json" `
  -Body '{"friendId":"8d81b7ad-5f4d-474f-b2a9-5f8d39cf6f6e"}'
```

### Удаление друга

```http
DELETE /users/{userId}/friends/{friendId}
```

Удаляет связь дружбы между двумя пользователями.

```powershell
Invoke-RestMethod -Method Delete -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends/8d81b7ad-5f4d-474f-b2a9-5f8d39cf6f6e"
```

### Просмотр списка друзей

```http
GET /users/{userId}/friends?limit=20&offset=0
```

Возвращает список друзей с пагинацией.

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends?limit=20&offset=0" `
  -Headers @{ Accept = "application/json" }
```

### Публикация поста

```http
POST /users/{userId}/posts
```

Создает новый пост пользователя.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/posts" `
  -ContentType "application/json" `
  -Body '{
    "content": "Сегодня отличный день для релиза!",
    "visibility": "friends"
  }'
```

## Как открыть спецификацию

1. Откройте [Swagger Editor](https://editor.swagger.io/).
2. Вставьте содержимое файла `openapi.yaml`.
3. Проверьте список эндпоинтов, схемы данных и примеры ответов.

## Возможные коды ответов

- `200 OK` - данные успешно получены.
- `201 Created` - сущность создана.
- `204 No Content` - удаление выполнено, тело ответа пустое.
- `400 Bad Request` - некорректный запрос.
- `404 Not Found` - сущность не найдена.
- `409 Conflict` - конфликт состояния, например дружба уже существует.

## Формат ошибки

```json
{
  "error": {
    "code": "FRIENDSHIP_ALREADY_EXISTS",
    "message": "Friendship already exists",
    "details": null
  }
}
```

## Итог

Лабораторная показывает этап проектирования API до реализации сервера. В результате получается понятный контракт, по которому backend, frontend и тесты могут разрабатываться независимо.
