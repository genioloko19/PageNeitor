# Contribuir a Pageneitor

Gracias por querer mejorar Pageneitor.

## Requisitos

- Windows 10/11
- Python 3.10+
- Git
- Ollama opcional para probar funciones de IA local

## Configuración

```bash
git clone https://github.com/genioloko19/PageNeitor.git
cd PageNeitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Ejecuta la aplicación:

```bash
python app.py
```

Compila el ejecutable:

```bat
build.bat
```

## Flujo de trabajo

1. Crea una rama descriptiva:
   - `feature/asistente-enlaces`
   - `fix/cierre-al-inicio`
   - `docs/readme`
2. Mantén cambios pequeños y enfocados.
3. Prueba manualmente las funciones afectadas.
4. Ejecuta las comprobaciones:

```bash
python -m compileall app.py backend build_windows.py
node --check frontend/scripts/app.js
node --check frontend/scripts/api.js
```

5. Haz commit con mensajes convencionales:

```text
feat: añadir vista de dominio
fix: evitar cierre por DLL bloqueada
docs: actualizar guía de instalación
```

6. Abre un Pull Request describiendo:
   - Qué cambia.
   - Cómo se probó.
   - Capturas si aplica.
   - Riesgos o migraciones de datos.

## Reglas

- No subir `dist/`, `build/`, `.pyinstaller_build/`, `.venv/`, `pageneitor.db`, `backups/` ni logs.
- No incluir credenciales, tokens, `.env` ni datos personales.
- Mantener los recursos offline en `frontend/vendor/`.
- Respetar el estilo visual y la arquitectura existente.
- No romper la compatibilidad de la base de datos sin migración.
- Las operaciones destructivas deben confirmar, respaldar y poder deshacerse.

## Reportar problemas

Usa las plantillas de issues del repositorio. Incluye:

- Versión de Pageneitor.
- Versión de Windows y Python.
- Pasos para reproducir.
- Log de `%APPDATA%\Pageneitor\pageneitor_crash.log` si existe.
- Capturas o texto del error.
