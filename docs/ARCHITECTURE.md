# Arquitectura

## Visión general

Pageneitor combina un backend Python/Flask con una interfaz web empaquetada en PySide6/QtWebEngine.

```text
PySide6 Window
  └── QWebEngineView
        └── Frontend HTML/CSS/JS
              └── fetch() → Flask API (127.0.0.1:5241)
                    ├── SQLite (%APPDATA%\Pageneitor)
                    ├── Scraper OpenGraph
                    └── Ollama local
```

## Componentes

### `app.py`
- Inicia Flask en un hilo daemon.
- Crea la ventana Qt.
- Configura el perfil persistente de WebEngine.
- Gestiona descargas, errores fatales y copia al cerrar.

### `backend/server.py`
- Expone la API REST.
- Sirve el frontend.
- Instrumenta llamadas API para analítica local.
- Conecta enlaces, credenciales, subenlaces, dominios, chat, respaldos y estadísticas.

### `backend/database.py`
- Esquema SQLite y migraciones.
- Enlaces, perfiles, categorías, credenciales, subenlaces.
- Gamificación, chat, sugerencias de dominio, auditoría.
- Copias automáticas y restauración segura.
- Ajustes de aplicación.

### `backend/domain_utils.py`
- Extracción de host.
- Normalización de dominio raíz.
- Soporte para subdominios y sufijos multi-etiqueta.

### `backend/domain_service.py`
- Agrupación por dominio.
- Escaneo programado/debounced.
- Sugerencias con reglas + Ollama.
- Validación de acciones.
- Aplicación, descarte y deshacer.

### `backend/chat_assistant.py`
- Intenciones en español.
- Búsqueda y ranking de enlaces.
- Comandos de dominios, sugerencias y enlaces.
- Integración con Ollama y fallback determinista.

### `backend/link_assistant.py`
- Extracción de URLs.
- Metadatos y deduplicación.
- Clasificación con Ollama.
- Propuesta de nuevas categorías/perfiles.
- Confirmación y commit.

### `backend/analytics_service.py`
- Snapshot de KPIs.
- Estadística descriptiva.
- Calidad de datos y actividad.
- Insights con Ollama.
- Nube de palabras cacheada.

### Frontend
- `index.html`: estructura y modales.
- `scripts/api.js`: cliente REST.
- `scripts/app.js`: estado, vistas, gráficas y eventos.
- `styles/glass.css`: temas, componentes y capas.
- `vendor/`: librerías offline.

## Datos

```text
%APPDATA%\Pageneitor\
├── pageneitor.db
├── backups\
├── exports\
├── webengine\
└── pageneitor_crash.log
```

## Seguridad

- El servidor escucha solo en `127.0.0.1`.
- No se envían credenciales a Ollama.
- Las operaciones destructivas crean respaldo y se pueden deshacer.
- La analítica es local y sin datos sensibles.
