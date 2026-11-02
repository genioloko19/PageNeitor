---
description: Actualizar la rama local de forma segura
---

Sincroniza el repositorio:

1. Ejecuta `git fetch --all --prune`.
2. Ejecuta `git status --short`.
3. Si no hay cambios locales, ejecuta `git pull --rebase`.
4. Si hay cambios locales, muestra qué archivos están modificados y pregunta antes de continuar.
5. No hagas push ni commit en este comando.
6. Resume el estado final de la rama.
