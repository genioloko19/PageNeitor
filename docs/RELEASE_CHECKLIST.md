# Checklist de release

## Antes de etiquetar

- [ ] Actualizar `README.md` con la versión.
- [ ] Actualizar `CHANGELOG.md`.
- [ ] Actualizar `CITATION.cff`.
- [ ] Verificar que `pageneitor.db`, `dist/`, `build/`, `.pyinstaller_build/`, `backups/` y logs estén ignorados.
- [ ] Ejecutar `python -m compileall app.py backend build_windows.py`.
- [ ] Ejecutar `node --check frontend/scripts/app.js` y `node --check frontend/scripts/api.js`.
- [ ] Compilar con `build.bat`.
- [ ] Probar `dist\Pageneitor\Pageneitor.exe`.
- [ ] Probar migración con una copia de la base real.
- [ ] Verificar exportación/importación `.db` y `.json`.

## Empaquetado

```powershell
Compress-Archive -Path "dist\Pageneitor\*" -DestinationPath "Pageneitor-vX.Y.Z-win64.zip" -CompressionLevel Optimal
```

## Publicación

- [ ] Crear tag `vX.Y.Z`.
- [ ] Crear release con notas desde `RELEASE_NOTES_vX.Y.Z.md`.
- [ ] Adjuntar `Pageneitor-vX.Y.Z-win64.zip`.
- [ ] Verificar descarga y arranque desde el ZIP.
- [ ] Revisar descripción, homepage y topics del repositorio.

## Después de publicar

- [ ] Verificar la release en GitHub.
- [ ] Comprobar que `main` y el tag apuntan al commit esperado.
- [ ] Anunciar cambios.
