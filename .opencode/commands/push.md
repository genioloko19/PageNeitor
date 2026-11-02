---
description: Publicar la rama actual en origin
---

1. Ejecuta `git status` y confirma que no quedan cambios sin commitear.
2. Ejecuta `git fetch origin --prune`.
3. Comprueba si la rama tiene upstream.
4. Si no lo tiene, publica con `git push -u origin <rama>`.
5. Si el push es rechazado, no uses `--force`; informa y propone `git pull --rebase`.
6. Muestra el resultado final.
