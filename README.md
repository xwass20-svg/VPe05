# VPe05 — Loki + Grafana: сбор и визуализация логов

Домашнее задание: развёртывание стека логирования (Loki + Grafana), дашборд с таблицей и круговой диаграммой, тестовое приложение криптобиржи с отправкой логов в Loki.

## Структура

```
VPe05/
├── Loki+Grafana/
│   └── docker-compose.yml   # сервисы loki и grafana
├── app/
│   └── crypto_backend.py    # эмулятор бэкенда + send_log_to_loki
└── README.md
```

## Часть 1. Стек и Data Source

### Запуск

```bash
cd Loki+Grafana
docker compose up -d
```

Сервисы:

| Сервис  | URL / порт              | Доступ внутри сети compose |
|---------|-------------------------|----------------------------|
| Grafana | http://localhost:3000   | —                          |
| Loki    | http://localhost:3100   | `http://loki:3100`         |

Логин Grafana (задан в compose): `admin` / `admin`.

Оба сервиса в сети `logging` — Grafana обращается к Loki по имени контейнера.

### Подключение Loki в Grafana

1. Откройте http://localhost:3000
2. **Connections → Data sources → Add data source → Loki**
3. URL: `http://loki:3100`
4. **Save & test**

> Loki — это API, не веб-интерфейс. Страница `http://localhost:3100` в браузере «не сайт»; UI — только Grafana.

## Часть 2. Дашборд

Создайте дашборд с двумя панелями:

1. **Таблица** последних логов, например:
   ```logql
   {app="crypto_exchange"}
   ```
2. **Pie chart** распределения по уровню:
   ```logql
   sum by (level) (count_over_time({app="crypto_exchange"}[$__range]))
   ```

Метки логов: `app`, `level` (`debug` / `info` / `warning` / `error`).

## Часть 3. Отправка логов

В `app/crypto_backend.py`:

- `emulate_crypto_backend_event()` — эмуляция операций криптобиржи (ордера, сделки, балансы, депозиты/выводы, ошибки) со случайными значениями и паузами.
- `send_log_to_loki(message, level=...)` — **POST** на `/loki/api/v1/push`.

### Запуск эмулятора

Убедитесь, что Loki запущен, затем:

```bash
cd app
python -u crypto_backend.py
```

Остановка: `Ctrl+C`.

Тест одной отправки:

```bash
python -c "from crypto_backend import send_log_to_loki; print(send_log_to_loki('hello from crypto_backend', level='info'))"
```

## Полезные команды

```bash
# статус контейнеров
docker compose -f Loki+Grafana/docker-compose.yml ps

# остановка стека
docker compose -f Loki+Grafana/docker-compose.yml down

# логи Loki
docker logs loki --tail 50
```

## Требования

- Docker Desktop (Engine running)
- Python 3.10+ (для эмулятора; внешние зависимости не нужны)
