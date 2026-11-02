---
description: Probar, commitear y publicar la tarea actual
---

Prepara y publica la tarea actual:

1. Ejecuta `git status` y `git diff`.
2. Ejecuta las comprobaciones mínimas:
   - `python -m compileall app.py backend build_windows.py`
   - `node --check frontend/scripts/app.js`
   - `node --check frontend/scripts/api.js`
3. Verifica que no se incluyan secretos, bases de datos, copias, logs ni artefactos.
4. Añade solo los archivos relacionados con la tarea.
5. Crea un commit con Conventional Commits.
6. Haz push a la rama actual.
7. Si hay conflictos, fallos o el push es rechazado, detente e informa.
8. Nunca uses `git push --force`.
