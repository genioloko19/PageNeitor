# Pageneitor v3.9.0 — Windows

Primera release completa de Pageneitor publicada desde el repositorio.

## Descargar

- `Pageneitor-v3.9.0-win64.zip`
- Descomprime y ejecuta `Pageneitor.exe`.

## Novedades principales

### Asistente de enlaces
Pega una o varias URLs y deja que Pageneitor detecte el dominio, compruebe duplicados y proponga tema, perfil y etiquetas con reglas + Ollama. Puede sugerir temas o perfiles nuevos, pero solo se crean tras confirmación.

### Estadísticas y KPIs
Nueva sección con KPIs, estadística descriptiva, calidad de datos, actividad, top dominios, rendimiento de la API y análisis con IA local. Usa Chart.js, Highcharts y Plotly locales.

### Vista detallada por dominio
Cada dominio tiene una página completa con KPIs, gráficas y todos sus enlaces con miniatura, edición, eliminación y apertura.

### Fondo por capas
- Tema actual.
- Nube de palabras generada por Ollama, decorativa y rotativa.
- Información del sistema: KPIs, actividad, dominios, nivel, logros y estado de Ollama.

### Datos protegidos
La base sigue viviendo en `%APPDATA%\Pageneitor`. Recompilar no borra enlaces, credenciales, subenlaces, conversaciones ni copias de seguridad.

## Requisitos

- Windows 10/11 64-bit
- Ollama opcional para las funciones de IA local

## Integridad

- Copia automática antes de operaciones delicadas.
- Exportación/importación `.db` y `.json`.
- Auditoría y deshacer para fusiones de dominios.

## Notas

- El ejecutable no está firmado; SmartScreen puede mostrar una advertencia.
- Las credenciales se guardan localmente en SQLite. Protege tu cuenta de Windows y tus respaldos.
- Highcharts se usa bajo su licencia gratuita para uso personal/no comercial.

## Enlaces

- [Repositorio](https://github.com/genioloko19/PageNeitor)
- [Changelog](CHANGELOG.md)
- [Licencia](LICENSE)
