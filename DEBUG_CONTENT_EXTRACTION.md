# Отладка извлечения контента страницы

## 🐛 Проблема: Модель не видит текст со страницы

Если вы видите текст на странице, но модель говорит "контекст не содержит информации", это проблема извлечения контента.

### ✅ Что исправлено:

1. **Расширены селекторы для различных типов сайтов:**
   - Atlassian/Confluence: `.wiki-content`, `[data-testid="page-content"]`
   - Документация: `.article-content`, `.page-content`
   - Блоги: Habr, Medium, WordPress
   - E-commerce: стандартные product классы

2. **Добавлены fallback механизмы:**
   - Попытка `<article>` если основной селектор не сработал
   - Очистка body от `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`
   - Последний fallback: полный `documentElement`

3. **Фильтрация мусора:**
   - Удаление DIAG маркеров: `/DIAG[\s\S]*?(?=\n|$)/g`
   - Схлопывание множественных пробелов и переводов строк
   - Trim и нормализация whitespace

4. **Логирование для отладки:**
   - `content.js`: логи в консоль браузера
   - `main.py`: предупреждения в логи бэкенда

---

## 🔍 Как проверить извлечение контента:

### 1. В консоли браузера (DevTools → Console):

```javascript
// Откройте проблемную страницу
// Откройте DevTools (F12) → Console
// Вы увидите логи Chrome-bot:

[Chrome-bot] Main content selector matched: article-content
[Chrome-bot] Final text length: 8543
```

**Что проверить:**
- ✅ `Final text length` > 500 chars → хорошо
- ⚠️ `Final text length` < 200 chars → проблема
- ⚠️ `WARNING: Very short text` → плохое извлечение

### 2. В логах бэкенда (терминал):

```bash
# Запустите бэкенд и смотрите логи:
cd backend_lg
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8010

# После запроса увидите:
INFO: Chat request: message='что такое пакет инструментов' url='https://...' text_len=8543
```

**Что проверить:**
- ✅ `text_len > 500` → хорошо
- ⚠️ `WARNING: Page text contains DIAG markers` → мусор в тексте
- ⚠️ `WARNING: Short page text` → плохое извлечение

---

## 🛠️ Решение проблем:

### Проблема 1: "DIAG" маркеры в тексте

**Причина:** Страница содержит диагностические метки

**Решение:** ✅ Уже исправлено в `content.js`:
```javascript
.replace(/DIAG[\s\S]*?(?=\n|$)/g, '') // Remove DIAG lines
```

### Проблема 2: Короткий текст (< 200 chars)

**Причина:** Селекторы не подходят для данного сайта

**Решение:**
1. Откройте DevTools → Elements
2. Найдите основной контент страницы
3. Посмотрите его класс/id (например: `.main-article`)
4. Добавьте селектор в `content.js` (строка 109-120):

```javascript
let mainEl = document.querySelector(
    'main,[role="main"],article,[role="article"],' +
    // ... existing selectors ...
    '.main-article,.your-custom-class' // ← Добавьте сюда
);
```

### Проблема 3: Динамический контент (SPA)

**Причина:** Контент загружается асинхронно

**Решение:** ✅ Уже есть `MutationObserver` (строка 254):
```javascript
const mainContentObserver = new MutationObserver((mutations, observer) => {
    if (document.querySelector('main,[role="main"],article,...')) {
        setTimeout(sendContext, 300);
        observer.disconnect();
    }
});
```

Если не помогает:
1. Увеличьте задержку: `setTimeout(sendContext, 1000)` (строка 250)
2. Добавьте второй таймер: `setTimeout(sendContext, 3000)` (строка 257)

---

## 📋 Тестирование на конкретных сайтах:

### Atlassian (DevOps страница):

1. Откройте: https://www.atlassian.com/ru/devops/devops-tools
2. Консоль браузера → ожидаем:
   ```
   [Chrome-bot] Main content selector matched: ...
   [Chrome-bot] Final text length: 5000+ chars
   ```
3. Логи бэкенда → ожидаем:
   ```
   INFO: Chat request: text_len=5000+
   ```

### Habr:

1. Откройте любую статью на habr.com
2. Селекторы: `.article__content`, `.tm-article-body`
3. Ожидаемый результат: text_len > 3000

### Wikipedia:

1. Откройте любую статью
2. Селектор: `article` или `[role="article"]`
3. Ожидаемый результат: text_len > 5000

---

## 🚨 Экстренные меры:

### Если ничего не помогает:

1. **Временный хак - вручную вставьте текст:**
   ```javascript
   // В консоли браузера:
   const text = document.querySelector('main').innerText;
   console.log('Extracted:', text.length, 'chars');
   ```

2. **Проверьте, что расширение обновилось:**
   - `chrome://extensions`
   - Найдите Chrome-bot
   - Кликните "Обновить" (кнопка обновления)
   - Перезагрузите страницу

3. **Откройте issue с примером:**
   - URL проблемной страницы
   - Скриншот консоли браузера
   - Логи бэкенда
   - Класс/id основного контента (из DevTools → Elements)

---

## ✅ Чеклист для отладки:

- [ ] Открыл DevTools → Console
- [ ] Вижу логи `[Chrome-bot]`
- [ ] `Final text length` > 500?
- [ ] Проверил логи бэкенда
- [ ] `text_len` достаточно большой?
- [ ] Нет предупреждений о DIAG или short text?
- [ ] Попробовал перезагрузить страницу
- [ ] Обновил расширение в `chrome://extensions`

Если все чекбоксы ✅ но проблема осталась → сообщите с деталями!

---

## 📞 Поддержка:

При сообщении о проблеме укажите:
1. **URL страницы:** `https://...`
2. **Логи консоли браузера:** скриншот или текст
3. **Логи бэкенда:** вывод из терминала
4. **Селектор контента:** из DevTools → Elements
5. **Текст который видите на странице:** цитата

Это поможет быстро найти и исправить проблему! 🚀




