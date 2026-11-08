# Równa ściana

VPS-версия сайта с десятью польскими статьями. Запуск, деплой, база и домен описаны в [корневом README](../../README.md).

Тексты, каталог, изображения и оформление сохранены. Node 24 обслуживает HTML, поиск и Markdown из read-only SQLite snapshot. React используется только на сервере для шаблонов: браузер не получает React, Next.js или hydration. Меню, печать, копирование ссылок, сохранение чек-листов и согласие на аналитику обслуживает небольшой контроллер на обычном JavaScript. Прежние ключи localStorage сохранены; Google tag загружается только после согласия.

Проверки: `npm test`, `npm run db:seed`, `npm run build`, `npm run typecheck`; затем `npm start` и `npm run smoke`. Сборка создаёт автономный `dist/server.cjs` и CSS/JS с хешами; Docker runtime содержит только `dist`, публичные изображения и SQLite. CSS проходит через Tailwind/PostCSS, оптимизированные WebP сохраняют srcset и immutable cache. `VALIDATION*.md` — исторические отчёты до переноса.
