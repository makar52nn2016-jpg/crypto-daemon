# 🏢 Trudyagi — Autonomous Agent Corporation

> Преврати daemon в **4-рольную автономную команду** с LLM-агентами:
> **Бригадир** (планирование) → **Мастер** (техплан) → **Оператор** (исполнение) → **Контролёр** (проверка)

## 📁 Структура

```
trudyagi/
├── trudyagi.py          # CLI: init / run / demo / status / history / worklog / health
├── README.md            # этот файл
├── .env                 # настройки LLM (создаётся через init)
├── core/
│   ├── state.py         # state machine + per-task state.json
│   ├── orchestrator.py # 4-role pipeline
│   ├── llm_client.py    # OpenAI-compatible client (curl-based)
│   ├── demo_llm.py      # mock LLM для demo-режима (без API ключа)
│   └── worklog.py       # shared worklog (интеграция с основным daemon worklog)
├── roles/               # 4 системных промпта (markdown)
│   ├── brigadir.md      # Бригадир — планирует, распределяет
│   ├── master.md        # Мастер — техплан, инструменты
│   ├── controller.md    # Контролёр — независимая проверка
│   └── operator.md     # Оператор — исполняет шаги
└── tasks/<task_id>/     # per-task артефакты + state.json
    ├── state.json
    ├── brigadir.yaml
    ├── master_plan.yaml
    ├── operator_report.yaml
    ├── controller_review.yaml
    └── step-N.json
```

## 🚀 Быстрый старт

### 1. Demo mode (без API ключа)

```bash
cd trudyagi
python trudyagi.py demo "Earn \$1.50 today via Frantic #136"
```

Demo LLM возвращает canned responses для каждой роли. Это показывает как pipeline работает.

### 2. Real mode (нужен LLM API)

```bash
cd trudyagi
python trudyagi.py init         # создаёт .env
nano .env                       # заполни LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
python trudyagi.py health       # проверь что LLM живой
python trudyagi.py run "Earn \$1.50 today via Frantic #136"
```

### 3. Проверить результат

```bash
python trudyagi.py status       # статус последней задачи
python trudyagi.py history 10   # последние 10 задач
python trudyagi.py worklog 5    # последние 5 worklog записей
```

## 🎭 Роли

### Бригадир (Brigadir)
**Цель от пользователя** → **декомпозиция на 1-3 подзадачи** с измеримыми критериями успеха.

**Вход:** `"заработай $1.50 сегодня"`  
**Выход:** `brigadir.yaml` с `goal`, `success_criteria[]`, `subtasks[]`

### Мастер (Master)
**Подзадача** → **технический план из 3-7 атомарных шагов** с конкретными инструментами.

**Вход:** подзадача от Бригадира + контекст доступных APIs из `KNOWLEDGE_BASE.md`  
**Выход:** `master_plan.yaml` с `steps[]` (action + tool + expected_output + verification)

### Оператор (Operator)
**План** → **выполнение шаг за шагом** с сохранением артефактов.

**Вход:** план от Мастера  
**Выход:** `operator_report.yaml` + `step-N.json` для каждого шага (содержит команду + stdout + статус)

### Контролёр (Controller)
**Артефакты Оператора** → **независимая верификация через прямой API call** (не доверяет отчёту Оператора).

**Вход:** план + отчёт Оператора  
**Выход:** `controller_review.yaml` с `verdict: PASS | FAIL | NEEDS_REVISION` + список замечаний

## 🔄 Pipeline

```
PENDING → PLANNING → EXECUTING → REVIEWING ─┬→ COMPLETED ✅
                         ↑           ↓          ├→ FAILED ❌
                         │      NEEDS_REVISION ├→ NEEDS_REVISION (retry)
                         └───────────────────┘
```

Если Контролёр говорит `NEEDS_REVISION` — цикл повторяется (макс 2 ревизии).

## 🔧 Поддерживаемые LLM провайдеры

Любой OpenAI-compatible endpoint:

| Провайдер | LLM_BASE_URL | LLM_MODEL пример |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Anthropic via proxy | `https://api.anthropic-proxy.com/v1` | `claude-3-5-sonnet-20241022` |
| Z.ai GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Ollama local | `http://localhost:11434/v1` | `llama3.2` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |

## 🔌 Интеграция с daemon

Daemon workflow может триггерить trudyagi автоматически при новых событиях:

```python
# В daemon.py — после нахождения новой Frantic bounty
subprocess.run([
    "python", "trudyagi/trudyagi.py", "run",
    f"Claim Frantic bounty #{bounty_number} — title: {title}"
])
```

Trudyagi пишет в общий `worklog.md` (разделяемый с daemon'ом).

## 🛡️ Безопасность

- **Shell commands** выполняются через `subprocess.run` с `timeout=60s`
- **Blocklist** для опасных паттернов: `rm -rf`, `sudo`, `mkfs`, `dd of=`, fork bombs
- **Secrets** через env vars (не логируются в worklog)
- **Per-task изоляция**: каждый task_id имеет свою директорию + артефакты

## 📊 Пример вывода

```bash
$ python trudyagi.py demo "Earn $1.50 today via Frantic #136"
🎭 DEMO mode — running pipeline for:
   "Earn $1.50 today via Frantic #136"

[Бригадир] parsed goal → 2 subtasks (1.2s)
[Мастер]   created 3-step plan (0.8s)
[Оператор] executed 3 steps, all SUCCESS (4.5s)
  - step-1: GitHub daemon workflow_runs check
  - step-2: Frantic #136 claim status check
  - step-3: stompstart.com publication status
[Контролёр] verified — verdict: PASS (1.3s)

============================================================
Final state: COMPLETED
Task ID:     task-abc12345
Goal:        Earn $1.50 today via Frantic #136
Artifacts in tasks/task-abc12345/:
  - brigadir.yaml
  - master_plan.yaml
  - operator_report.yaml
  - controller_review.yaml
  - step-1.json
  - step-2.json
  - step-3.json
```

## 🎯 Что это даёт

**Без trudyagi:** Daemon находит bounty → пишет в worklog → ждёт что кто-то (ты или я) сделает задачу.

**С trudyagi:** Daemon находит bounty → запускает `trudyagi run "Claim Frantic #137"` → Бригадир разбирает цель → Мастер делает план → Оператор выполняет (claim, deliver, push) → Контролёр проверяет → если PASS — задача закрыта автономно, без человеческого вмешательства.

Daemon становится **autonomous bounty-claiming machine** с 4-уровневой системой качества.
