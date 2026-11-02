# Política de seguridad

## Versiones soportadas

| Versión | Soporte |
| --- | --- |
| 3.9.x | ✅ |
| 3.8.x | ⚠️ solo correcciones críticas |
| anteriores | ❌ |

## Reportar una vulnerabilidad

No abras un issue público para vulnerabilidades.

Envía un reporte privado con:

- Descripción del problema.
- Versión de Pageneitor.
- Pasos para reproducirlo.
- Impacto potencial.
- Prueba de concepto, si existe.
- Sugerencia de mitigación.

Usa la opción **Security → Report a vulnerability** del repositorio de GitHub.

## Alcance

Pageneitor es una aplicación local. Los riesgos relevantes incluyen:

- Exposición de credenciales guardadas en SQLite.
- Ejecución de URLs o contenido no confiable.
- Manipulación de respaldos `.db` o `.json`.
- Ejecución local de binarios de Ollama.
- Fugas de datos en prompts enviados a modelos locales.

## Recomendaciones

- Mantén Windows actualizado.
- Usa una cuenta de usuario con permisos limitados.
- No compartas `%APPDATA%\Pageneitor`.
- Protege tus respaldos.
- Descarga binarios solo desde este repositorio.
- Revisa los modelos locales antes de usarlos.
