"""
Build script for Pageneitor Windows Executable (.exe).

Key reliability rules:
  1. Stop any running Pageneitor instance first (otherwise PyInstaller cannot
     delete locked DLLs and leaves a half-deleted dist folder).
  2. Build in an isolated folder. The current working dist/Pageneitor is only
     replaced after the new build finished successfully, so a failed build can
     never destroy the executable that currently works.
  3. Remove stale build artifacts (the old build/Pageneitor/_internal with a
     python311.dll from a previous Python version is what caused the
     "Failed to load Python DLL" startup crash).
  4. Verify the packaged runtime before replacing the working app.
"""

import os
import sys
import glob
import time
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
FINAL_APP_DIR = os.path.join(DIST_DIR, "Pageneitor")

BUILD_ROOT = os.path.join(BASE_DIR, ".pyinstaller_build")
BUILD_WORK = os.path.join(BUILD_ROOT, "work")
BUILD_DIST = os.path.join(BUILD_ROOT, "dist")
BUILD_SPEC = os.path.join(BUILD_ROOT, "spec")
STAGED_APP_DIR = os.path.join(BUILD_DIST, "Pageneitor")


def log(message=""):
    print(message, flush=True)


def stop_running_app():
    """Kills the app and its QtWebEngine children so files can be replaced."""
    log("[1/6] Cerrando instancias de Pageneitor en ejecución...")

    # /T also terminates QtWebEngineProcess.exe children.
    subprocess.run(
        ["taskkill", "/F", "/T", "/IM", "Pageneitor.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Give Windows a moment to release file handles.
    for _ in range(10):
        time.sleep(0.3)
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Pageneitor.exe"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if "Pageneitor.exe" not in (result.stdout or ""):
            break

    time.sleep(0.5)


def _make_writable(func, path, exc_info):
    try:
        os.chmod(path, 0o777)
        func(path)
    except Exception:
        pass


def remove_path(path, retries=6):
    """Deletes a file/folder, retrying on Windows file-lock errors."""
    if not os.path.exists(path):
        return

    last_error = None
    for attempt in range(retries):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, onerror=_make_writable)
            else:
                os.chmod(path, 0o777)
                os.remove(path)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.7)

    raise RuntimeError(f"No se pudo eliminar '{path}'.\nÚltimo error: {last_error}")


def clean_old_artifacts():
    log("[2/6] Limpiando artefactos antiguos (build/ dist obsoleto/spec)...")

    # Old root build/ from previous Python versions (python311.dll problem).
    remove_path(os.path.join(BASE_DIR, "build"))

    # Old generated spec: the build script no longer depends on it.
    remove_path(os.path.join(BASE_DIR, "Pageneitor.spec"))

    # Isolated build workspace for this run.
    remove_path(BUILD_ROOT)
    os.makedirs(BUILD_WORK, exist_ok=True)
    os.makedirs(BUILD_DIST, exist_ok=True)
    os.makedirs(BUILD_SPEC, exist_ok=True)


def build_command():
    sep = ";" if sys.platform == "win32" else ":"
    frontend_src = os.path.join(BASE_DIR, "frontend")
    add_data_frontend = f"{frontend_src}{sep}frontend"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=Pageneitor",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--distpath={BUILD_DIST}",
        f"--workpath={BUILD_WORK}",
        f"--specpath={BUILD_SPEC}",
        f"--add-data={add_data_frontend}",
        "--hidden-import=backend",
        "--hidden-import=backend.database",
        "--hidden-import=backend.scraper",
        "--hidden-import=backend.server",
        "--hidden-import=backend.seed_data",
        "--hidden-import=backend.ollama_service",
        "--hidden-import=backend.chat_assistant",
        "--hidden-import=backend.domain_service",
        "--hidden-import=backend.domain_utils",
        "--hidden-import=backend.analytics_service",
        "--hidden-import=backend.link_assistant",
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=requests",
        "--hidden-import=sqlite3",
        "--hidden-import=PySide6.QtWebEngineWidgets",
        "--hidden-import=PySide6.QtWebEngineCore",
        "app.py",
    ]

    icon_path = os.path.join(BASE_DIR, "frontend", "assets", "icon.ico")
    if os.path.exists(icon_path):
        cmd.insert(-1, f"--icon={icon_path}")

    return cmd


def verify_build():
    log("[4/6] Verificando el ejecutable generado...")

    exe_path = os.path.join(STAGED_APP_DIR, "Pageneitor.exe")
    if not os.path.exists(exe_path):
        raise RuntimeError("No se generó Pageneitor.exe en la carpeta de compilación.")

    internal_dir = os.path.join(STAGED_APP_DIR, "_internal")
    if not os.path.isdir(internal_dir):
        raise RuntimeError("No se generó la carpeta _internal del ejecutable.")

    python_dlls = glob.glob(os.path.join(internal_dir, "python3*.dll"))
    if not python_dlls:
        raise RuntimeError(
            "El ejecutable no incluye la DLL de Python. "
            "Compilación incompleta: no se publicará."
        )

    required = [
        os.path.join(internal_dir, "PySide6", "Qt6WebEngineCore.dll"),
        os.path.join(internal_dir, "PySide6", "QtWebEngineProcess.exe"),
        os.path.join(internal_dir, "PySide6", "resources", "icudtl.dat"),
        os.path.join(internal_dir, "PySide6", "resources", "qtwebengine_resources.pak"),
    ]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        raise RuntimeError(
            "Faltan componentes de QtWebEngine:\n  " + "\n  ".join(missing)
        )

    if not os.path.exists(os.path.join(internal_dir, "frontend", "index.html")):
        # Some PyInstaller versions place bundled data directly in _internal.
        if not os.path.exists(os.path.join(STAGED_APP_DIR, "frontend", "index.html")):
            raise RuntimeError("El frontend no quedó incluido en el ejecutable.")

    log(f"      Ejecutable verificado: {exe_path}")
    return exe_path


def publish_build():
    log("[5/6] Publicando la nueva versión en dist/Pageneitor...")

    os.makedirs(DIST_DIR, exist_ok=True)
    backup_dir = os.path.join(DIST_DIR, "Pageneitor_old")
    remove_path(backup_dir)

    had_previous = os.path.isdir(FINAL_APP_DIR)
    if had_previous:
        try:
            os.rename(FINAL_APP_DIR, backup_dir)
        except Exception as exc:
            raise RuntimeError(
                "La carpeta dist/Pageneitor sigue bloqueada. Cierra Pageneitor "
                "y vuelve a ejecutar la compilación.\n"
                f"Detalle: {exc}"
            )

    try:
        shutil.move(STAGED_APP_DIR, FINAL_APP_DIR)
    except Exception:
        # Restore the previous working build if publishing fails.
        if had_previous and os.path.isdir(backup_dir):
            try:
                os.rename(backup_dir, FINAL_APP_DIR)
            except Exception:
                pass
        raise

    remove_path(backup_dir)

    # Clean the isolated workspace only after a successful publish.
    remove_path(BUILD_WORK)


def build():
    log("=" * 62)
    log("  Compilando Pageneitor para Windows con PyInstaller")
    log("=" * 62)

    try:
        stop_running_app()
        clean_old_artifacts()

        log("[3/6] Ejecutando PyInstaller (esto puede tardar varios minutos)...")
        cmd = build_command()
        log("      " + " ".join(cmd))
        log("")

        result = subprocess.run(cmd, cwd=BASE_DIR)
        if result.returncode != 0:
            log("")
            log(f"[Error] La compilación falló. Código de error: {result.returncode}")
            log("        Tu versión anterior en dist/Pageneitor NO fue modificada.")
            return False

        verify_build()
        publish_build()

        log("")
        log("=" * 62)
        log("  ¡COMPILACIÓN EXITOSA!")
        log(f"  Ejecutable: {os.path.join(FINAL_APP_DIR, 'Pageneitor.exe')}")
        log("  Datos y copias de seguridad: %APPDATA%\\Pageneitor")
        log("=" * 62)
        return True

    except Exception as exc:
        log("")
        log(f"[Error] {exc}")
        log("        Tu versión anterior en dist/Pageneitor NO fue modificada.")
        return False


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
