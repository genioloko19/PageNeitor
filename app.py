"""
Pageneitor - Main Desktop Application Launcher v3.9.1.
Combines Python backend with high-performance Chromium WebEngine.
Includes global crash logger, graceful error recovery, and robust port management.
"""

import sys
import os
import threading
import time
import socket
import traceback
import faulthandler
from datetime import datetime
from urllib.request import urlopen, Request

# ============================================================
# BOOTSTRAP: never die silently because of a missing dependency.
# ============================================================
def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _data_dir():
    override = os.environ.get("PAGENEITOR_DATA_DIR")
    if override:
        data_dir = os.path.abspath(os.path.expanduser(override))
    else:
        data_dir = os.path.join(
            os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
            "Pageneitor"
        )
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DATA_DIR = _data_dir()
CRASH_LOG_PATH = os.path.join(DATA_DIR, "pageneitor_crash.log")

try:
    _crash_stream = open(CRASH_LOG_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_crash_stream)
except Exception:
    _crash_stream = None

def _show_fatal(message, title="Pageneitor - Error de inicio"):
    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now()}] FATAL: {message}\n")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(message), title, 0x10)
    except Exception:
        pass
    try:
        print(f"[FATAL] {message}")
    except Exception:
        pass

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
    from PySide6.QtCore import QUrl, Qt, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
except Exception as exc:
    _show_fatal(
        "No se pudieron cargar las dependencias de la interfaz (PySide6 / QtWebEngine).\n\n"
        f"Detalle: {exc}\n\n"
        "Instala las dependencias con:  pip install -r requirements.txt\n"
        f"Registro: {CRASH_LOG_PATH}"
    )
    raise SystemExit(1)

def global_exception_handler(exctype, value, tb):
    error_trace = "".join(traceback.format_exception(exctype, value, tb))
    print(f"\n[CRASH DETECTED]:\n{error_trace}")
    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[{datetime.now()}] CRASH OCCURRED:\n{error_trace}\n{'='*60}\n")
    except Exception:
        pass
    
    # Show native alert if Qt is active
    try:
        QMessageBox.critical(
            None,
            "Pageneitor - Error Inesperado",
            f"Ocurrió un error inesperado. Los detalles se guardaron en pageneitor_crash.log:\n\n{value}"
        )
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_handler

# Import backend modules safely
try:
    from backend.server import app as flask_app
except Exception as exc:
    _show_fatal(
        "No se pudo iniciar el motor interno de Pageneitor.\n\n"
        f"Detalle: {exc}\n\n"
        f"Registro: {CRASH_LOG_PATH}"
    )
    raise SystemExit(1)

PORT = 5241
SERVER_URL = f"http://127.0.0.1:{PORT}"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

def start_backend():
    """Runs Flask server in background daemon thread."""
    try:
        if not is_port_in_use(PORT):
            flask_app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now()}] FLASK RUN ERROR: {traceback.format_exc()}\n")

def is_server_ready():
    try:
        with urlopen(f"{SERVER_URL}/api/status", timeout=0.8) as resp:
            return resp.status == 200
    except Exception:
        return False

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._reload_attempts = 0

    def renderProcessTerminated(self, terminationStatus, exitCode):
        print(f"[WebEngine] Process terminated (status: {terminationStatus}, code: {exitCode}).")
        if self._reload_attempts < 5:
            self._reload_attempts += 1
            QTimer.singleShot(500 * self._reload_attempts, lambda: self.load(QUrl(SERVER_URL)))
        else:
            _show_fatal(
                "El motor de visualización se cerró repetidamente.\n"
                "Cierra la aplicación y vuelve a abrirla.",
                "Pageneitor - WebEngine"
            )

class PageneitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pageneitor - Banco Visual de Enlaces & Antitab Manager")
        self.resize(1300, 860)
        self.setMinimumSize(960, 600)

        # Set App Icon if exists
        icon_path = os.path.join(_app_dir(), "frontend", "assets", "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Persistent WebEngine storage in the stable data folder.
        # Otherwise themes/settings are lost between versions/rebuilds.
        web_dir = os.path.join(DATA_DIR, "webengine")
        os.makedirs(web_dir, exist_ok=True)
        try:
            profile = QWebEngineProfile.defaultProfile()
            profile.setPersistentStoragePath(os.path.join(web_dir, "storage"))
            profile.setCachePath(os.path.join(web_dir, "cache"))
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            profile.downloadRequested.connect(self.handle_download)
        except Exception as exc:
            print(f"[WebEngine] Could not configure persistent profile: {exc}")

        # WebEngine setup with custom page
        self.webview = QWebEngineView()
        self.page = CustomWebEnginePage(self.webview)
        self.webview.setPage(self.page)
        
        # Configure WebEngine Settings
        settings = self.webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self.setCentralWidget(self.webview)

        # Start loading loop
        if is_server_ready():
            self.webview.load(QUrl(SERVER_URL))
        else:
            # Show temporary loading screen and poll until server is ready
            loading_html = """
            <!DOCTYPE html>
            <html>
            <head>
              <style>
                body {
                  margin: 0; background: #070a12; color: #f8fafc; font-family: 'Segoe UI', sans-serif;
                  display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh;
                }
                .spinner {
                  width: 44px; height: 44px; border: 3px solid rgba(99,102,241,0.2);
                  border-top-color: #6366f1; border-radius: 50%; animation: spin 0.8s linear infinite;
                }
                @keyframes spin { to { transform: rotate(360deg); } }
                h2 { margin-top: 18px; font-size: 18px; font-weight: 700; }
                p { color: #94a3b8; font-size: 13px; }
              </style>
            </head>
            <body>
              <div class="spinner"></div>
              <h2>Iniciando Pageneitor...</h2>
              <p>Cargando banco visual de enlaces y base de datos local</p>
            </body>
            </html>
            """
            self.webview.setHtml(loading_html)
            self.poll_timer = QTimer(self)
            self.poll_timer.timeout.connect(self.check_server_and_redirect)
            self.poll_timer.start(250)

    def check_server_and_redirect(self):
        if is_server_ready():
            self.poll_timer.stop()
            self.webview.load(QUrl(SERVER_URL))

    def handle_download(self, item):
        """QtWebEngine needs an explicit handler or database exports do nothing."""
        try:
            suggested = item.suggestedFileName() or "pageneitor_backup.db"
            export_dir = os.path.join(DATA_DIR, "exports")
            os.makedirs(export_dir, exist_ok=True)
            default_path = os.path.join(export_dir, suggested)

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar copia de seguridad",
                default_path,
                "Todos los archivos (*.*)"
            )
            if not path:
                item.cancel()
                return

            item.setDownloadDirectory(os.path.dirname(path))
            item.setDownloadFileName(os.path.basename(path))
            item.accept()
        except Exception as exc:
            print(f"[Download] Error: {exc}")
            try:
                item.cancel()
            except Exception:
                pass

    def closeEvent(self, event):
        """Best-effort safety snapshot before the app closes."""
        try:
            req = Request(f"{SERVER_URL}/api/backup/on-close", method="POST")
            with urlopen(req, timeout=2):
                pass
        except Exception:
            pass
        super().closeEvent(event)

def main():
    # 1. Start Python backend server in daemon thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # 2. Initialize Qt Application
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Pageneitor")
    qt_app.setOrganizationName("Pageneitor")

    # 3. Create and show main window
    window = PageneitorWindow()
    window.show()

    sys.exit(qt_app.exec())

if __name__ == "__main__":
    main()
