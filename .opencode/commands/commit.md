---
description: Crear un commit seguro de la tarea actual
---

1. Revisa `git status` y `git diff`.
2. Ejecuta las comprobaciones mínimas del proyecto.
3. Comprueba que no se incluyan secretos, `pageneitor.db`, `backups/`, `dist/`, `build/`, `.pyinstaller_build/`, `.venv/`, `__pycache__/` ni logs.
4. Añade solo los archivos relacionados.
5. Crea un commit con mensaje Conventional Commits.
6. No hagas push.
7. Muestra el hash y el resumen del commit.
