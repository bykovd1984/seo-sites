# SEO sites

Репозиторий самостоятельных статейных сайтов. Первый сайт — **Równa ściana**: десять польских статей о подготовке стен и дефектах окраски.

Код, оформление, статьи и изображения: [sites/rowna-sciana](sites/rowna-sciana). Тексты перенесены без изменений; [контрольные суммы](migration-articles.json). Даты проверки источников и статус редакционных черновиков сохранены.

## Локальный запуск

Node.js 24 LTS:

```powershell
cd sites/rowna-sciana
npm ci
npm run db:seed
npm run dev
```

Адрес разработки: http://127.0.0.1:3000. Для production: `npm run build`, затем `npm start`.
Проверки: `npm test`, `npm run typecheck`; HTTP smoke: `npm run smoke` при работающем сервере.

## Автоматический деплой

Push в `main` запускает [.github/workflows/deploy.yml](.github/workflows/deploy.yml). PR проверяются на GitHub-hosted runner; production job работает только из main этого репозитория на отдельном runner `seo-sites` того же VPS, где размещены Grammar Guru и Grammar Flashcards.

Docker собирает Next.js standalone и собственную SQLite `/app/data/content.sqlite` из Markdown. Runtime открывает её только для чтения. Данные пользователей отсутствуют, поэтому внешняя общая PostgreSQL не требуется. Каждый образ содержит согласованные код и контент; изменение статей применяется новым деплоем.

Перед заменой production проверяется отдельный кандидат: health, все десять страниц, обложки, поиск, 404 и robots. При ошибке после переключения восстанавливается предыдущий Docker-образ вместе с его базой.

Контейнер: `seo-rowna-sciana`. Адрес на VPS: `127.0.0.1:5005`. Compose и отметка коммита: `/opt/seo-sites/rowna-sciana/`. Удаление образов других сервисов и изменение их конфигурации в скриптах отсутствуют.

## Домен и индексация

Домен подключён 01.11.2026: **https://rownasciana.site/**. В Namecheap BasicDNS через браузер настроены A `@` → `65.108.142.86` (Automatic) и CNAME `www` → `rownasciana.site.` (30 min). Почтовые настройки сохранены. Конфигурация [ops/rowna-sciana.caddy](ops/rowna-sciana.caddy) установлена в `/etc/caddy/domains/rowna-sciana.caddy` и импортирована из Caddyfile. HTTPS включён автоматически; `www` перенаправляется на основной домен с сохранением пути и query string. HTTP перенаправляется на HTTPS.

`noindex, nofollow` и запрет robots сохранены до отдельного разрешения индексации. Независимая техническая экспертиза и вычитка польским редактором ещё не выполнены. Обложки — подписанные AI-иллюстрации, не фотографии испытаний.

Исходные SEO-исследования скопированы в локальную папку `research/`, исключённую из Git. Исторические VALIDATION-файлы относятся к прежней Cloudflare-версии. Актуальные проверки переноса фиксируются отдельно.
