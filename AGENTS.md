# Instrucciones del proyecto Pageneitor

## Contexto

Pageneitor es una aplicación de escritorio Windows:

- Python + Flask + SQLite en el backend.
- PySide6/QtWebEngine en el escritorio.
- Frontend HTML/CSS/JS con librerías locales en `frontend/vendor/`.
- Ollama local para IA.
- Los datos de usuario viven en `%APPDATA%\Pageneitor`.

## Flujo Git

### Al comenzar una tarea

1. Ejecutar `git fetch --all --prune`.
2. Ejecutar `git status --short`.
3. Si no hay cambios locales y la rama tiene upstream, ejecutar `git pull --rebase`.
4. Si hay cambios locales, resumirlos antes de mezclar.
5. Nunca descartar cambios del usuario sin confirmación.

### Antes de hacer commit

1. Revisar `git status` y `git diff`.
2. Ejecutar las pruebas o comprobaciones relevantes.
3. Asegurarse de que no se incluyen secretos ni datos de usuario.
4. Verificar que no se añaden `dist/`, `build/`, `.pyinstaller_build/`, `.venv/`, `pageneitor.db`, `backups/`, logs ni `__pycache__/`.
5. Añadir solo archivos relacionados con la tarea.

### Mensajes de commit

Usar Conventional Commits:

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `perf: ...`
- `test: ...`
- `chore: ...`

### Al terminar una tarea

1. Ejecutar las pruebas.
2. Hacer commit con Conventional Commits.
3. Hacer push a la rama actual.
4. Si la rama es `main` y el push directo está permitido, publicarlo.
5. Si el repositorio exige Pull Request o el push es rechazado, crear una rama y abrir un PR.
6. Si el push falla, no usar `--force`; informar del error.

## Comprobaciones mínimas

```bash
python -m compileall app.py backend build_windows.py
node --check frontend/scripts/app.js
node --check frontend/scripts/api.js
```

Para cambios visuales o de flujo:

```bat
build.bat
```

Y probar `dist\Pageneitor\Pageneitor.exe`.

## Seguridad

- Nunca commitear `.env`, tokens, contraseñas ni bases de datos de usuario.
- No enviar credenciales a Ollama.
- No borrar `dist/` manualmente si hay una instancia abierta.
- No ejecutar `git reset --hard`, `git clean -fd` ni `git push --force` sin confirmación explícita.

## Datos

- La base local de desarrollo `pageneitor.db` no se versiona.
- Las copias y exports no se versionan.
- Los recursos offline de `frontend/vendor/` sí se versionan.
