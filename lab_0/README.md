# Social Network API

Проект содержит спецификацию REST API для социальной сети в формате OpenAPI.

## Файлы

- `openapi.yaml` — полная спецификация OpenAPI 3.0.3

## Быстрый старт

1. Откройте [Swagger Editor](https://editor.swagger.io/).
2. Вставьте содержимое файла `openapi.yaml`.
3. Просмотрите и протестируйте эндпоинты.

## Базовые параметры

- Base URL: `http://localhost:8080/api/v1`
- Формат данных: `application/json`
- Идентификаторы: UUID

## Основные операции API

### 1) Просмотр анкеты пользователя

`GET /users/{userId}`

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1" `
  -Headers @{ Accept = "application/json" }
```

### 2) Добавление друга

`POST /users/{userId}/friends`

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends" `
  -ContentType "application/json" `
  -Body '{"friendId":"8d81b7ad-5f4d-474f-b2a9-5f8d39cf6f6e"}'
```

### 3) Удаление друга

`DELETE /users/{userId}/friends/{friendId}`

```powershell
Invoke-RestMethod -Method Delete -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends/8d81b7ad-5f4d-474f-b2a9-5f8d39cf6f6e"
```

### 4) Просмотр списка друзей

`GET /users/{userId}/friends?limit=20&offset=0`

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/friends?limit=20&offset=0" `
  -Headers @{ Accept = "application/json" }
```

### 5) Публикация поста

`POST /users/{userId}/posts`

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/users/af1f0f3b-8e90-4c8f-87a6-2a46db2a53f1/posts" `
  -ContentType "application/json" `
  -Body '{
    "content": "Сегодня отличный день для релиза!",
    "visibility": "friends"
  }'
```

## Примеры кодов ответа

- `200 OK` — успешное чтение данных
- `201 Created` — сущность создана
- `204 No Content` — успешное удаление без тела ответа
- `400 Bad Request` — некорректный запрос
- `404 Not Found` — сущность не найдена
- `409 Conflict` — конфликт состояния (например, дружба уже существует)

## Пример формата ошибки

```json
{
  "error": {
    "code": "FRIENDSHIP_ALREADY_EXISTS",
    "message": "Friendship already exists",
    "details": null
  }
}
```
