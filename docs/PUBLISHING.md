# Публикация на GitHub

Локальный Git-репозиторий уже создан с основной веткой `main`. До публикации создайте пустой репозиторий на GitHub без автоматически добавленных README, `.gitignore` и лицензии.

## Проверка перед первым commit

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py codex_memory tests
git status --short
git check-ignore -v history.txt memory/example/memory.json .env secret.key
git diff -- .
```

В выводе `git status` не должно быть реальных историй, содержимого `memory/`, `.env`, ключей, баз и логов.

## Первый commit и push

Замените `<USERNAME>` и `<REPOSITORY>` на значения вашего пустого GitHub-репозитория:

```powershell
git add .
git status --short
git commit -m "Initial Codex Memory MVP"
git remote add origin https://github.com/<USERNAME>/<REPOSITORY>.git
git push -u origin main
```

Перед `git commit` полезно выполнить `git diff --cached`, чтобы ещё раз увидеть всё, что попадёт в сеть.

Если remote `origin` уже существует, не добавляйте его повторно. Проверьте адрес:

```powershell
git remote -v
```

При необходимости исправьте:

```powershell
git remote set-url origin https://github.com/<USERNAME>/<REPOSITORY>.git
```

## Лицензия

Лицензия намеренно не выбрана автоматически. Перед публичным релизом владелец должен решить, будет ли проект MIT, Apache-2.0, другой open-source лицензией или останется без лицензии.
