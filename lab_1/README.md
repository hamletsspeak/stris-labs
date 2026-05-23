# Лабораторная 1: HTTP-сервис, балансировка, reverse proxy, кэш

## Что реализовано
- `GET /info` возвращает имя инстанса и текущее время.
- Запуск двух экземпляров сервиса:
  - `service-1` -> `localhost:8081`
  - `service-2` -> `localhost:8082`
- Nginx на `localhost:8080` работает как:
  - балансировщик нагрузки (Round Robin)
  - reverse proxy (единая точка входа)
- `GET /data?id=1` использует кэш (Redis):
  - первый запрос -> `source: generated`
  - повторный запрос -> `source: cache`

## Запуск
```bash
docker compose up --build -d
```

## Проверка части 1 и 2
```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8081/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8082/info"
```
В ответах должно отличаться поле `service`.

## Проверка части 3 и 4 (Round Robin + Reverse Proxy)
```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/info"
```
Сервисы в поле `service` должны чередоваться (`service-1`, `service-2`, ...).

## Проверка части 5 (кэш)
```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data?id=1"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/data?id=1"
```
Ожидаемо:
- первый ответ: `source = generated`
- второй ответ: `source = cache`

## Остановка
```bash
docker compose down
```
