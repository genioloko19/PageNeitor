# Changelog

Todos los cambios importantes de Pageneitor se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [3.9.1] - 2026-11-02

### Añadido
- Manual visual completo con capturas reales de la interfaz.
- Capturas para panel principal, dominios, detalle de dominio, asistente, chat, credenciales, estadísticas, base de datos, notificaciones y temas.
- Enlaces profundos de OpenCode para abrir chat, credenciales, notificaciones y paneles concretos.
- Enlace al manual visual desde las notas de release.

### Cambiado
- README reestructurado como introducción + manual para usuarios + sección técnica.
- Panel de Control ampliado para mostrar todas las pestañas sin recortes.
- Capturas optimizadas en WebP para reducir el peso del repositorio.

### Corregido
- Pluralización en el asistente de enlaces.
- Evitado el solapamiento de toasts en capturas de demostración.

## [3.9.0] - 2026-11-02

### Añadido
- Asistente de inserción de enlaces para una o varias URLs.
- Detección de dominio principal, grupos existentes y duplicados.
- Clasificación automática de tema, perfil y etiquetas con reglas + Ollama.
- Propuesta y creación confirmada de categorías y perfiles nuevos.
- Vista completa de estadísticas, KPIs y calidad de datos.
- Estadística descriptiva con media, mediana, moda, desviación y percentiles.
- Actividad por hora/día, top dominios, temas, perfiles y etiquetas.
- Medición local de llamadas API y eventos de interfaz.
- Análisis de métricas agregadas con Ollama.
- Integración local de Chart.js, Highcharts y Plotly.
- Vista detallada por dominio con KPIs, gráficas y enlaces editables.
- Capa de fondo con nube de palabras generada por Ollama.
- Rotación configurable de la nube de palabras.
- Capa de información del sistema con KPIs, actividad, dominios, nivel, logros y estado de Ollama.
- Exportación de estadísticas a JSON.
- Nuevos ajustes de retención de métricas y rotación visual.

### Cambiado
- README, metadatos y estructura del repositorio preparados para releases.
- Analítica antigua separada de la nueva vista de estadísticas.
- Mejoras de rendimiento y caché en análisis LLM.

### Corregido
- Conflictos entre la analítica del dashboard y la nueva vista avanzada.
- Persistencia de sesiones y restauración tras reinicios.
- Recuperación de enlaces archivados al eliminar un enlace principal fusionado.
- Invalidación de sugerencias obsoletas al cambiar la agrupación de subdominios.

## [3.8.0] - 2026

### Añadido
- Agrupación visual por dominio principal.
- Detección de subdominios y dominio raíz configurable.
- Sugerencias de Ollama para fusionar grupos o recuperar miniaturas.
- Campana de notificaciones persistente y toasts importantes.
- Fusión confirmada con archivo de enlaces secundarios.
- Auditoría y opción de deshacer.
- Navegación de dominios desde el chatbot.

## [3.7.0] - 2026

### Añadido
- Asistente flotante persistente.
- Búsqueda conversacional sobre enlaces, temas y perfiles.
- Sesiones de chat guardadas en SQLite.
- Respuestas con Ollama y fallback local.
- Historial de conversaciones y recuperación tras reinicio.

## [3.6.0] - 2026

### Añadido
- Credenciales multiusuario por enlace.
- Subenlaces asociados por enlace.
- Panel de exportación/importación de base de datos.
- Copias automáticas y manuales.
- Persistencia fuera del ejecutable en `%APPDATA%\Pageneitor`.
- Recursos offline sin CDN.
- Compilación segura en carpeta aislada.

### Corregido
- Pérdida de datos al recompilar.
- Bloqueos de DLLs por instancias abiertas.
- Arranque fallido por restos de versiones anteriores.

## [3.5.0] - 2026

### Añadido
- Gestión ampliada de perfiles, categorías y enlaces.
- Sistema de trofeos y niveles.
- Panel de control ampliado.
- Integración inicial con Ollama.

## [3.0.0] - 2026

### Añadido
- Interfaz Glassmorphism.
- 10 temas y 3 modos visuales.
- Arquitectura Zero-Flicker.
- Dashboard de métricas y gráficas.
- Gamificación y sistema antitab.

---

[Unreleased]: https://github.com/genioloko19/PageNeitor/compare/v3.9.1...HEAD
[3.9.1]: https://github.com/genioloko19/PageNeitor/compare/v3.9.0...v3.9.1
[3.9.0]: https://github.com/genioloko19/PageNeitor/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/genioloko19/PageNeitor/compare/v3.7.0...v3.8.0
[3.7.0]: https://github.com/genioloko19/PageNeitor/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/genioloko19/PageNeitor/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/genioloko19/PageNeitor/compare/v3.0.0...v3.5.0
