# ⚡ Pageneitor

**Banco visual de enlaces, gestor antitab, asistente local con IA y centro de analítica para tu navegador.**

[![Release](https://img.shields.io/github/v/release/genioloko19/PageNeitor?style=flat-square)](https://github.com/genioloko19/PageNeitor/releases)
[![License](https://img.shields.io/github/license/genioloko19/PageNeitor?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?style=flat-square)](https://www.microsoft.com/windows)
[![Offline](https://img.shields.io/badge/Offline-100%25-34d399?style=flat-square)](#-privacidad-y-funcionamiento-local)

Pageneitor evita que acumules decenas o cientos de pestañas abiertas. Guarda tus enlaces en un banco visual con miniaturas, etiquetas, notas, perfiles, credenciales y subenlaces; los agrupa por dominio y utiliza **Ollama** localmente para clasificar, buscar y proponer mejoras sin enviar tus datos a la nube.

> **Versión actual:** `v3.9.0`  
> **Descargar:** [Última release para Windows](https://github.com/genioloko19/PageNeitor/releases/latest)

---

## ✨ Características principales

### 📚 Banco visual de enlaces
- Tarjetas con miniatura, favicon, dominio, tema, perfil y etiquetas.
- Búsqueda por título, URL, dominio, descripción, etiquetas y notas.
- Favoritos, pendientes, leídos, archivados y perfiles de navegador.
- Arquitectura **Zero-Flicker**: las tarjetas se actualizan sin recargar la vista.

### 🔐 Credenciales multiusuario
- Varias cuentas por enlace: alias, usuario, contraseña y notas.
- Mostrar/ocultar y copiar credenciales.
- Los datos permanecen en la base local.

### 🧩 Subenlaces por enlace
- Guarda otras pestañas del mismo sitio dentro de un enlace principal.
- Añade subenlaces uno a uno o en lote.
- Abre todos, marca como leído o elimina.
- Detecta enlaces del mismo dominio ya guardados.

### 🌐 Agrupación inteligente por dominio
- `docs.github.com`, `gist.github.com` y `github.com` se agrupan bajo `github.com`.
- Agrupación de subdominios configurable.
- Mosaico de miniaturas por grupo.
- Fusión opcional de enlaces: los secundarios se archivan, nunca se borran.
- Copia de seguridad, auditoría y deshacer.

### 🤖 Asistente flotante persistente
- Busca en tus enlaces, muestra temas, perfiles y dominios.
- Abre enlaces desde el chat.
- Historial de conversaciones guardado en SQLite.
- Respuestas cortas con Ollama o motor local determinista.
- Comandos como `ver dominios`, `fusiona github.com`, `aplica la sugerencia 2` o `deshaz la última acción`.

### 🪄 Asistente de inserción de enlaces
- Pega una o varias URLs.
- Detecta dominio principal, duplicados y metadatos.
- Clasifica con reglas + Ollama.
- Propone tema, perfil, etiquetas y, si hace falta, **nuevos temas/perfiles**.
- Nada se guarda ni se crea sin confirmación.

### 📊 Estadísticas, KPIs y calidad de datos
- KPIs generales y por dominio.
- Estadística descriptiva: media, mediana, moda, desviación estándar y percentiles.
- Distribuciones, actividad por hora/día, top dominios y temas.
- Calidad: enlaces sin miniatura, sin tema, sin perfil, sin etiquetas o duplicados.
- Rendimiento de la API y eventos locales.
- Análisis con Ollama bajo demanda.
- Modo principiante y modo avanzado.
- Exportación JSON.

### 🎨 Interfaz y capas visuales
- 10 temas de color × 3 modos: oscuro, claro y alto contraste.
- Capa 0: tema y degradados.
- Capa 1: nube de palabras generada por Ollama, decorativa y rotativa.
- Capa 2: información del sistema (KPIs, actividad, dominios, nivel, logros y estado de Ollama).
- **100% responsive**.

### 🏆 Gamificación
- 26+ trofeos por perfiles, temas, calidad, poda y actividad.
- Niveles, XP y decay por inactividad.
- Celebración con confeti y sonido de consola.

### 💾 Integridad de datos
- Base de datos en `%APPDATA%\Pageneitor`.
- Copias automáticas antes de operaciones delicadas.
- Exportar/importar `.db` y `.json`.
- Restauración de copias y opción de deshacer.
- La base **no** se guarda dentro del ejecutable: recompilar no borra datos.

---

## 🚀 Instalación

### Opción 1: descargar el ejecutable

1. Ve a [Releases](https://github.com/genioloko19/PageNeitor/releases/latest).
2. Descarga `Pageneitor-v3.9.0-win64.zip`.
3. Descomprime la carpeta.
4. Ejecuta `Pageneitor.exe`.

> Windows puede mostrar SmartScreen porque el ejecutable no está firmado. Verifica que venga del repositorio oficial.

### Opción 2: ejecutar desde el código

Requisitos:

- Windows 10/11
- Python 3.10 o superior
- [Ollama](https://ollama.com/) opcional, recomendado para IA local

```bash
git clone https://github.com/genioloko19/PageNeitor.git
cd PageNeitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

También puedes usar:

```bat
run.bat
```

---

## 🧠 Ollama local

Pageneitor detecta Ollama en:

- `./ollama.exe` junto al proyecto
- `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`
- `PATH`

Si está instalado pero apagado, Pageneitor intenta iniciarlo. Si no está disponible, usa un motor local determinista con datos reales.

```bash
ollama pull qwen2.5-coder:7b
ollama serve
```

El modelo se selecciona en **Panel de Control → Ollama**.

---

## 🏗️ Compilar el ejecutable

```bat
build.bat
```

El resultado queda en:

```text
dist\Pageneitor\Pageneitor.exe
```

`build_windows.py`:

1. Cierra instancias abiertas de Pageneitor.
2. Limpia artefactos antiguos y DLLs bloqueadas.
3. Compila en `.pyinstaller_build/`.
4. Verifica Python, QtWebEngine y recursos.
5. Solo entonces reemplaza `dist/Pageneitor/`.

Si la compilación falla, la versión anterior se conserva.

---

## 🗂️ Estructura del proyecto

```text
PageNeitor/
├── app.py                  # Lanzador PySide6 + Flask
├── backend/
│   ├── server.py           # API REST
│   ├── database.py         # SQLite, copias, migraciones
│   ├── scraper.py          # Metadatos OpenGraph
│   ├── ollama_service.py   # Integración con Ollama
│   ├── chat_assistant.py   # Asistente conversacional
│   ├── domain_service.py   # Dominios y sugerencias LLM
│   ├── link_assistant.py   # Inserción y clasificación de enlaces
│   ├── analytics_service.py# KPIs, estadística y word cloud
│   └── domain_utils.py     # Normalización de dominios
├── frontend/
│   ├── index.html
│   ├── scripts/
│   ├── styles/
│   └── vendor/             # Librerías offline
├── electron/               # Alternativa Electron (opcional)
├── build_windows.py
├── requirements.txt
└── README.md
```

---

## 🗄️ Dónde están tus datos

```text
%APPDATA%\Pageneitor\pageneitor.db
%APPDATA%\Pageneitor\backups\
%APPDATA%\Pageneitor\exports\
%APPDATA%\Pageneitor\webengine\
%APPDATA%\Pageneitor\pageneitor_crash.log
```

Puedes usar una ubicación portátil:

```bat
set PAGENEITOR_DATA_DIR=D:\MisDatos\Pageneitor
```

---

## 🔌 API local

El backend expone una API REST en `http://127.0.0.1:5241`.

| Área | Endpoints principales |
|---|---|
| Estado | `/api/status`, `/api/stats` |
| Enlaces | `/api/links`, `/api/links/<id>` |
| Credenciales | `/api/links/<id>/credentials` |
| Subenlaces | `/api/links/<id>/sublinks` |
| Asistente | `/api/chat`, `/api/chat/sessions` |
| Inserción | `/api/links/assistant/preview`, `/commit` |
| Dominios | `/api/domains/groups`, `/detail`, `/suggestions` |
| Analítica | `/api/analytics/overview`, `/insights` |
| Nube | `/api/wordcloud` |
| Respaldos | `/api/backup/export-db`, `/export-json`, `/import-db`, `/import-json` |

---

## 🔒 Privacidad y funcionamiento local

- La aplicación corre en `127.0.0.1`.
- Los enlaces, credenciales, conversaciones y métricas viven en tu equipo.
- Ollama se ejecuta localmente.
- No se envían credenciales a ningún modelo.
- La analítica es local y configurable en retención.
- Las librerías del frontend están empaquetadas; no depende de CDNs.

---

## 🧪 Verificación

```bash
python -m compileall app.py backend build_windows.py
node --check frontend/scripts/app.js
node --check frontend/scripts/api.js
```

---

## 🤝 Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md) y el [Código de Conducta](CODE_OF_CONDUCT.md).

---

## 🛡️ Seguridad

Consulta [SECURITY.md](SECURITY.md) para reportar vulnerabilidades de forma privada.

---

## 📄 Licencia

MIT. Consulta [LICENSE](LICENSE) y [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## ⭐ Apoya el proyecto

Si Pageneitor te ayuda a mantener el navegador limpio, deja una estrella en el repositorio.

[github.com/genioloko19/PageNeitor](https://github.com/genioloko19/PageNeitor)
