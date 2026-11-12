# Site DSS — выбор площадки распределительного склада

Локальный учебный MVP 0.3.0: данные и геометрия, AHP, база знаний, прогноз, оптимизация потоков, риск, рекомендации, Streamlit и Apache Superset. Все текущие исходные сведения моковые; реальных участков к покупке система не предлагает.

## Установка и запуск

Требуется Python 3.12 или 3.13. Команды выполняются из корня проекта.

```bash
python3.12 -m venv .venv312
.venv312/bin/python -m pip install -r requirements.lock
.venv312/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv312/bin/python scripts/smoke.py
.venv312/bin/python -m pytest -q
.venv312/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

[Открыть интерфейс](http://127.0.0.1:8501)

[Руководство ЛПР](docs/USER_GUIDE.md)

## Контрольные проверки расчетов

1. Спрос = ×1, CAPEX = 900 млн ₽, совместный риск ≥90% ⇒ допустимой площадки нет.
2. Спрос ×0.75 и те же условия ⇒ рекомендована площадка B, U≈.8333, площадка A дешевле и остается допустимой альтернативой.
3. CAPEX 600 млн ₽ ⇒ допустимых площадок нет.

Фиксированные запросы — `config/baseline.json` и `config/reduced_demand.json`. Для запуска через CLI использовать команду:

```bash
.venv312/bin/python -m site_dss.cli --mvp --allow-demo --request config/reduced_demand.json
```

Расчет создает каталог `reports/runs/<run_id>`; CLI переключает BI на этот запуск. В форме BI переключается только явной кнопкой. [Локальный Superset](http://127.0.0.1:8089/superset/dashboard/site-dss/) запускается отдельно.

## Документы

- [Паспорт СППР](docs/Паспорт%20СППР.md), [печатная версия](output/pdf/Паспорт%20СППР.pdf).
- [Руководство ЛПР](docs/USER_GUIDE.md).
- [Спецификация данных и вычислений](docs/DATA_AND_MODELS.md).
- [Оптимизационная модель](docs/OPTIMIZATION.md).
- [AHP-книга](output/AHP.xlsx) — отдельный проверочный расчет с формулами.

Входные данные находятся в `data/mock/`; перенос прежних отчетов не мешает новым расчетам.

## Superset

Команды выполняются из корня проекта. Сначала выполните расчет в CLI, чтобы создать локальную BI-базу (см. выше), затем:

```bash
python3 scripts/setup_superset.py
python3 scripts/run_superset.py
```

Установщик запускается обычным `python3`. Он устанавливает закрепленный `uv`, загружает Python 3.11.14 в `.runtime/python/`, создает `.superset-venv/` и устанавливает Apache Superset 4.1.4 из `bi/requirements-superset.lock`. Для первой установки нужен интернет; на macOS для сборки зависимостей нужны Command Line Tools (`xcode-select --install`). Окружение расчетного ядра `.venv312` используется отдельно.

Настройка применяет миграции, создает администратора и дашборд, проверяет вход и REST-запросы всех шести представлений, включая фильтр чужого `run_id`, и обновляет экспорт дашборда. 
Повторный запуск сохраняет учетные данные и обновляет существующие объекты. Журнал установки: `.runtime/superset-setup.log`. 
Если BI-база еще не создана или указан несовместимый Python, скрипт выводит команду исправления.

[Открыть дашборд](http://127.0.0.1:8089/superset/dashboard/site-dss/). Учетные данные находятся в `.runtime/superset/admin.json` и не включаются в Git. Экспорт дашборда: [superset_dashboard.zip](bi/superset_dashboard.zip).

Повторная проверка без запуска сервера: `python3 scripts/run_superset.py --verify`. Если порт занят, выберите другой: `python3 scripts/run_superset.py --port 8090`. 

## Ограничения

Данные синтетические. Малая калибровочная выборка и недопокрытие прогнозных интервалов ограничивают применение к реальному спросу. Инструкции по интерпретации результатов приведены в руководстве ЛПР и паспорте.
