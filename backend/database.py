"""
Database module for Pageneitor v3.9.
Handles SQLite persistence for:
- Links with multi-account credentials and associated sub-links / tabs
- Topics/categories and browser profiles with full CRUD
- Console-style gamification with decay and 26+ trophies
- Bulletproof backup & restore engine (SQLite file + Portable JSON + Auto-backups)
"""

import sqlite3
import os
import sys
import json
import hashlib
import shutil
import tempfile
import time
from datetime import datetime, timedelta

from backend.domain_utils import get_root_domain

APP_NAME = "Pageneitor"

def get_app_dir():
    """Directory that contains the executable / project (read-only assets)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_data_dir():
    """
    Stable, writable directory for the database and backups.

    It is intentionally NOT the executable folder: rebuilding the app deletes
    dist/Pageneitor, and using that folder would destroy the user's data.
    Set PAGENEITOR_DATA_DIR to use a portable/custom location.
    """
    override = os.environ.get("PAGENEITOR_DATA_DIR")
    if override:
        data_dir = os.path.abspath(os.path.expanduser(override))
    else:
        app_data = (
            os.environ.get('APPDATA')
            or os.environ.get('LOCALAPPDATA')
            or os.path.expanduser('~')
        )
        data_dir = os.path.join(app_data, APP_NAME)

    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def _is_valid_pageneitor_db(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) < 512:
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            conn.close()
        tables = {r[0] for r in rows}
        return "links" in tables
    except Exception:
        return False

def _legacy_db_candidates(target_db):
    """Old locations used by previous versions, ordered by newest first."""
    app_dir = get_app_dir()
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    local_appdata = os.environ.get('LOCALAPPDATA') or ''
    candidates = [
        os.path.join(app_dir, "pageneitor.db"),
        os.path.join(project_dir, "pageneitor.db"),
        os.path.join(local_appdata, APP_NAME, "pageneitor.db") if local_appdata else None,
    ]
    valid = []
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.abspath(candidate) == os.path.abspath(target_db):
            continue
        if _is_valid_pageneitor_db(candidate):
            valid.append(candidate)
    valid.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return valid

def _migrate_legacy_database(target_db):
    """
    Copies the most recent valid legacy DB into the stable data directory.
    Never overwrites an existing target database.
    """
    if os.path.exists(target_db):
        return False

    for legacy in _legacy_db_candidates(target_db):
        try:
            src = sqlite3.connect(legacy)
            dst = sqlite3.connect(target_db)
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
                src.close()
            print(f"[Database] Migrated legacy database from {legacy} to {target_db}")
            return True
        except Exception as e:
            print(f"[Database] Could not migrate {legacy}: {e}")
            try:
                if os.path.exists(target_db) and os.path.getsize(target_db) == 0:
                    os.remove(target_db)
            except Exception:
                pass

    return False

def get_db_path():
    data_dir = get_data_dir()
    target_db = os.path.join(data_dir, "pageneitor.db")
    if not os.path.exists(target_db):
        _migrate_legacy_database(target_db)
    return target_db

DB_PATH = get_db_path()
BACKUPS_DIR = os.path.join(get_data_dir(), "backups")
os.makedirs(BACKUPS_DIR, exist_ok=True)

# ============================================================
# APPLICATION SETTINGS (domain grouping / assistant behaviour)
# ============================================================
DEFAULT_DOMAIN_SETTINGS = {
    "group_subdomains": "1",
    "domain_scan_enabled": "1",
    "domain_scan_interval": "10",
    "domain_toast_enabled": "1",
    "domain_min_confidence": "0.6",
    "wordcloud_rotation": "60",
    "analytics_retention_days": "90",
}

# ============================================================
# AUTOMATIC ROLLING BACKUPS (ZERO DATA LOSS)
# ============================================================
def create_auto_backup(label="auto"):
    """Creates a timestamped snapshot of pageneitor.db."""
    try:
        if not os.path.exists(DB_PATH):
            return None
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"pageneitor_{label}_{timestamp}.db"
        backup_dest = os.path.join(BACKUPS_DIR, backup_filename)
        
        # Safe copy using sqlite online backup or direct copy
        conn = sqlite3.connect(DB_PATH)
        backup_conn = sqlite3.connect(backup_dest)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()

        # Prune old auto-backups, keep last 40. Manual backups are never pruned.
        all_backups = sorted(
            [
                os.path.join(BACKUPS_DIR, f)
                for f in os.listdir(BACKUPS_DIR)
                if f.endswith(".db") and "_manual_" not in f
            ],
            key=os.path.getmtime
        )
        if len(all_backups) > 40:
            for old_b in all_backups[:-40]:
                try:
                    os.remove(old_b)
                except Exception:
                    pass

        return backup_dest
    except Exception as e:
        print(f"[Backup] Warning creating auto backup: {e}")
        return None

def create_db_snapshot(dest_path=None):
    """
    Creates a consistent copy of the live database using SQLite's online
    backup API (safe even with WAL enabled). Returns the snapshot path.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError("La base de datos todavía no existe.")

    if not dest_path:
        fd, dest_path = tempfile.mkstemp(prefix="pageneitor_export_", suffix=".db")
        os.close(fd)

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()
    return dest_path

def get_db_info():
    """Returns storage diagnostics shown in the Control Panel."""
    info = {
        "db_path": DB_PATH,
        "backups_dir": BACKUPS_DIR,
        "data_dir": get_data_dir(),
        "exists": os.path.exists(DB_PATH),
        "size_kb": 0,
        "modified": None,
        "links": 0,
        "profiles": 0,
        "categories": 0,
        "credentials": 0,
        "sublinks": 0,
        "chat_sessions": 0,
        "backup_count": 0,
    }
    try:
        if os.path.exists(DB_PATH):
            stat = os.stat(DB_PATH)
            info["size_kb"] = round(stat.st_size / 1024, 1)
            info["modified"] = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        try:
            info["links"] = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            info["profiles"] = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
            info["categories"] = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            info["chat_sessions"] = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
            rows = conn.execute("SELECT credentials, sublinks FROM links").fetchall()
            for r in rows:
                try:
                    info["credentials"] += len(json.loads(r[0]) if r[0] else [])
                except Exception:
                    pass
                try:
                    info["sublinks"] += len(json.loads(r[1]) if r[1] else [])
                except Exception:
                    pass
        finally:
            conn.close()
        info["backup_count"] = len([
            f for f in os.listdir(BACKUPS_DIR) if f.endswith(".db")
        ])
    except Exception as e:
        info["error"] = str(e)
    return info

def get_auto_backups():
    """Lists all available auto-backup snapshots."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    results = []
    for f in os.listdir(BACKUPS_DIR):
        if f.endswith(".db") or f.endswith(".json"):
            fp = os.path.join(BACKUPS_DIR, f)
            stat = os.stat(fp)
            results.append({
                "filename": f,
                "path": fp,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "_mtime": stat.st_mtime,
            })
    results.sort(key=lambda x: x["_mtime"], reverse=True)
    for item in results:
        item.pop("_mtime", None)
    return results

# ============================================================
# EXPANDED CONSOLE TROPHIES CATALOG (26+ Trophies)
# ============================================================
TROPHIES_CATALOG = [
    # General & Antitab
    {
        "id": "first_link",
        "title": "Primer Vuelo",
        "tier": "bronze",
        "icon": "fa-feather-pointed",
        "category": "general",
        "xp": 50,
        "description": "Guarda tu primer enlace en Pageneitor y libera una pestaña."
    },
    {
        "id": "tab_closed",
        "title": "Misión Antitab",
        "tier": "bronze",
        "icon": "fa-door-open",
        "category": "general",
        "xp": 50,
        "description": "Abre un enlace guardado desde Pageneitor hacia tu navegador."
    },
    {
        "id": "batch_saver",
        "title": "Exterminador Masivo",
        "tier": "silver",
        "icon": "fa-layer-group",
        "category": "general",
        "xp": 150,
        "description": "Importa un lote masivo de pestañas para vaciar tu navegador de golpe."
    },
    {
        "id": "ram_hero",
        "title": "Guardián de la RAM",
        "tier": "silver",
        "icon": "fa-microchip",
        "category": "general",
        "xp": 200,
        "description": "Ahorra más de 1.5 GB de memoria RAM acumulada en pestañas cerradas."
    },
    {
        "id": "ram_titan",
        "title": "Titán de la Memoria",
        "tier": "gold",
        "icon": "fa-server",
        "category": "general",
        "xp": 350,
        "description": "Ahorra más de 3.0 GB de memoria RAM manteniendo tu navegador impecable."
    },
    {
        "id": "zen_collector",
        "title": "Coleccionista Zen",
        "tier": "gold",
        "icon": "fa-gem",
        "category": "general",
        "xp": 300,
        "description": "Alcanza al menos 15 enlaces activos en tu banco visual."
    },
    {
        "id": "platinum_zero",
        "title": "Soberano de Cero Pestañas",
        "tier": "platinum",
        "icon": "fa-crown",
        "category": "general",
        "xp": 500,
        "description": "Alcanza el Nivel 4 o superior dominando el arte de no acumular pestañas."
    },
    {
        "id": "diamond_immortal",
        "title": "Trascendencia Digital",
        "tier": "platinum",
        "icon": "fa-meteor",
        "category": "general",
        "xp": 800,
        "description": "Alcanza el Nivel 7 y desbloquea más de 12 trofeos de consola."
    },

    # Limpieza, Renovación, Credenciales y Sub-pestañas
    {
        "id": "link_perfectionist",
        "title": "Perfeccionista Web",
        "tier": "silver",
        "icon": "fa-certificate",
        "category": "calidad",
        "xp": 150,
        "description": "Guarda un enlace 100% completo: título, descripción, miniatura, tags y notas."
    },
    {
        "id": "vault_master",
        "title": "Guardián de Credenciales",
        "tier": "silver",
        "icon": "fa-key",
        "category": "calidad",
        "xp": 140,
        "description": "Registra credenciales seguras o múltiples cuentas en un enlace."
    },
    {
        "id": "sublink_architect",
        "title": "Árbol de Pestañas",
        "tier": "silver",
        "icon": "fa-folder-tree",
        "category": "calidad",
        "xp": 160,
        "description": "Asocia 3 o más sub-pestañas o enlaces secundarios a un mismo sitio."
    },
    {
        "id": "clean_pruner",
        "title": "Jardinero Digital",
        "tier": "bronze",
        "icon": "fa-scissors",
        "category": "limpieza",
        "xp": 75,
        "description": "Poda y elimina un enlace viejo para mantener tu banco fresco."
    },
    {
        "id": "deep_cleaner",
        "title": "Desintoxicación Extrema",
        "tier": "silver",
        "icon": "fa-broom",
        "category": "limpieza",
        "xp": 180,
        "description": "Elimina o depura 5 o más enlaces que ya no necesites."
    },
    {
        "id": "renovator",
        "title": "Renovador Incansable",
        "tier": "bronze",
        "icon": "fa-arrows-rotate",
        "category": "limpieza",
        "xp": 80,
        "description": "Edita y actualiza la información o notas de un enlace guardado."
    },
    {
        "id": "bookworm",
        "title": "Lector Voraz",
        "tier": "silver",
        "icon": "fa-book-open-reader",
        "category": "lectura",
        "xp": 120,
        "description": "Marca al menos 4 enlaces como leídos."
    },

    # Trofeos por Perfiles de Usuario
    {
        "id": "prof_personal",
        "title": "Maestro de Vida Personal",
        "tier": "bronze",
        "icon": "fa-heart",
        "category": "perfiles",
        "xp": 100,
        "description": "Organiza al menos 3 enlaces en el perfil 'Personal'."
    },
    {
        "id": "prof_work",
        "title": "Profesional Impecable",
        "tier": "silver",
        "icon": "fa-briefcase",
        "category": "perfiles",
        "xp": 120,
        "description": "Organiza al menos 3 enlaces en el perfil 'Trabajo'."
    },
    {
        "id": "prof_study",
        "title": "Erudito Digital",
        "tier": "silver",
        "icon": "fa-graduation-cap",
        "category": "perfiles",
        "xp": 120,
        "description": "Organiza al menos 3 enlaces en el perfil 'Estudio / Investigación'."
    },
    {
        "id": "prof_dev",
        "title": "Hacker de Consola",
        "tier": "silver",
        "icon": "fa-terminal",
        "category": "perfiles",
        "xp": 120,
        "description": "Organiza al menos 3 enlaces en el perfil 'Desarrollo & Tech'."
    },
    {
        "id": "prof_creator",
        "title": "Arquitecto de Identidades",
        "tier": "gold",
        "icon": "fa-id-card-clip",
        "category": "perfiles",
        "xp": 250,
        "description": "Crea o personaliza un nuevo perfil de navegador desde el Panel de Control."
    },

    # Trofeos por Temas & Categorías
    {
        "id": "cat_code",
        "title": "Ninja del Código",
        "tier": "bronze",
        "icon": "fa-code",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Desarrollo Web & Código'."
    },
    {
        "id": "cat_design",
        "title": "Ojo de Diseñador",
        "tier": "bronze",
        "icon": "fa-palette",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Diseño & UI/UX'."
    },
    {
        "id": "cat_ai",
        "title": "Pionero de la IA",
        "tier": "silver",
        "icon": "fa-brain",
        "category": "temas",
        "xp": 140,
        "description": "Guarda enlaces en la categoría de 'Inteligencia Artificial'."
    },
    {
        "id": "cat_docs",
        "title": "Guardián de Manuales",
        "tier": "bronze",
        "icon": "fa-book-bookmark",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Documentación & Guías'."
    },
    {
        "id": "cat_finance",
        "title": "Tiburón Financiero",
        "tier": "silver",
        "icon": "fa-money-bill-trend-up",
        "category": "temas",
        "xp": 140,
        "description": "Guarda enlaces en la categoría de 'Finanzas & Negocios'."
    },
    {
        "id": "cat_reading",
        "title": "Filósofo Moderno",
        "tier": "bronze",
        "icon": "fa-newspaper",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Lectura & Artículos'."
    },
    {
        "id": "cat_tools",
        "title": "Armería de Utilidades",
        "tier": "bronze",
        "icon": "fa-screwdriver-wrench",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Herramientas & Utilidades'."
    },
    {
        "id": "cat_media",
        "title": "Crítico Multimedia",
        "tier": "bronze",
        "icon": "fa-film",
        "category": "temas",
        "xp": 90,
        "description": "Guarda enlaces en la categoría de 'Entretenimiento & Videos'."
    },
    {
        "id": "polymath",
        "title": "Polímata Universal",
        "tier": "gold",
        "icon": "fa-shapes",
        "category": "temas",
        "xp": 350,
        "description": "Mantén enlaces catalogados en al menos 5 categorías distintas simultáneas."
    }
]

LEVELS = [
    {"level": 1, "min_xp": 0, "title": "Acumulador en Terapia"},
    {"level": 2, "min_xp": 120, "title": "Limpiador Novato"},
    {"level": 3, "min_xp": 280, "title": "Guardián de la RAM"},
    {"level": 4, "min_xp": 520, "title": "Organizador Táctico"},
    {"level": 5, "min_xp": 900, "title": "Cazador de Pestañas"},
    {"level": 6, "min_xp": 1450, "title": "Comandante Anti-Tabs"},
    {"level": 7, "min_xp": 2200, "title": "Arquitecto del Orden"},
    {"level": 8, "min_xp": 3200, "title": "Maestro Zen 0 Pestañas"}
]

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    # WAL + FULL gives crash-safe writes while allowing concurrent reads.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Profiles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        color TEXT NOT NULL DEFAULT '#6366f1',
        icon TEXT NOT NULL DEFAULT 'fa-user',
        description TEXT DEFAULT '',
        is_default INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Categories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        color TEXT NOT NULL DEFAULT '#3b82f6',
        icon TEXT NOT NULL DEFAULT 'fa-folder',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Links table with credentials and sublinks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        thumbnail_url TEXT DEFAULT '',
        favicon_url TEXT DEFAULT '',
        domain TEXT DEFAULT '',
        category_id INTEGER,
        profile_id INTEGER,
        tags TEXT DEFAULT '[]',
        credentials TEXT DEFAULT '[]',
        sublinks TEXT DEFAULT '[]',
        is_favorite INTEGER DEFAULT 0,
        is_read INTEGER DEFAULT 0,
        is_archived INTEGER DEFAULT 0,
        visit_count INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE SET NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles (id) ON DELETE SET NULL
    )
    """)

    # Migrations for existing links table
    cursor.execute("PRAGMA table_info(links)")
    link_cols = [c[1] for c in cursor.fetchall()]
    if "credentials" not in link_cols:
        cursor.execute("ALTER TABLE links ADD COLUMN credentials TEXT DEFAULT '[]'")
    if "sublinks" not in link_cols:
        cursor.execute("ALTER TABLE links ADD COLUMN sublinks TEXT DEFAULT '[]'")
    if "root_domain" not in link_cols:
        cursor.execute("ALTER TABLE links ADD COLUMN root_domain TEXT DEFAULT ''")
    if "merged_into_id" not in link_cols:
        cursor.execute("ALTER TABLE links ADD COLUMN merged_into_id INTEGER")

    # Gamification Table with last_active_at for decay
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gamification (
        id INTEGER PRIMARY KEY,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        level_title TEXT DEFAULT 'Acumulador en Terapia',
        trophies TEXT DEFAULT '[]',
        tabs_closed INTEGER DEFAULT 0,
        batch_count INTEGER DEFAULT 0,
        deleted_count INTEGER DEFAULT 0,
        updated_count INTEGER DEFAULT 0,
        last_active_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("PRAGMA table_info(gamification)")
    cols = [c[1] for c in cursor.fetchall()]
    if "deleted_count" not in cols:
        cursor.execute("ALTER TABLE gamification ADD COLUMN deleted_count INTEGER DEFAULT 0")
    if "updated_count" not in cols:
        cursor.execute("ALTER TABLE gamification ADD COLUMN updated_count INTEGER DEFAULT 0")
    if "last_active_at" not in cols:
        cursor.execute("ALTER TABLE gamification ADD COLUMN last_active_at TEXT DEFAULT ''")
        cursor.execute("UPDATE gamification SET last_active_at = datetime('now') WHERE last_active_at = ''")

    cursor.execute("SELECT COUNT(*) FROM gamification WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO gamification (id, xp, level, level_title, trophies, tabs_closed, batch_count, deleted_count, updated_count, last_active_at)
        VALUES (1, 80, 1, 'Acumulador en Terapia', '[]', 0, 0, 0, 0, datetime('now'))
        """)

    # Persistent chat assistant sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL DEFAULT 'Nueva conversación',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        data TEXT DEFAULT '{}',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")

    # Application settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Domain grouping suggestions generated by rules + Ollama
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS domain_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        root_domain TEXT NOT NULL,
        action TEXT NOT NULL,
        payload TEXT DEFAULT '{}',
        reason TEXT DEFAULT '',
        confidence REAL DEFAULT 0,
        signature TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        applied_at TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_domain_suggestions_status ON domain_suggestions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_domain_suggestions_domain ON domain_suggestions(root_domain)")

    # Audit / undo log for domain actions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS domain_action_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        root_domain TEXT DEFAULT '',
        payload_before TEXT DEFAULT '{}',
        payload_after TEXT DEFAULT '{}',
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        undone INTEGER DEFAULT 0
    )
    """)

    # Local telemetry used by the statistics section
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analytics_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_type TEXT DEFAULT '',
        entity_id TEXT DEFAULT '',
        action TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        session_id TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics_events(created_at)")

    # Cached LLM artifacts (word clouds, analytics insights)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS llm_cache (
        key TEXT PRIMARY KEY,
        kind TEXT DEFAULT '',
        payload TEXT DEFAULT '{}',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Default profiles
    cursor.execute("SELECT COUNT(*) FROM profiles")
    if cursor.fetchone()[0] == 0:
        default_profiles = [
            ("Personal", "personal", "#ec4899", "fa-heart", "Enlaces de ocio, compras, vida diaria", 1),
            ("Trabajo", "trabajo", "#3b82f6", "fa-briefcase", "Proyectos, herramientas de oficina, clientes", 0),
            ("Estudio / Investigación", "estudio", "#10b981", "fa-graduation-cap", "Cursos, artículos científicos, papers", 0),
            ("Desarrollo & Tech", "dev", "#8b5cf6", "fa-terminal", "Repositorios, snippets, documentación técnica", 0)
        ]
        cursor.executemany("""
        INSERT INTO profiles (name, slug, color, icon, description, is_default)
        VALUES (?, ?, ?, ?, ?, ?)
        """, default_profiles)

    # Default categories
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ("Desarrollo Web & Código", "dev", "#8b5cf6", "fa-code"),
            ("Diseño & UI/UX", "design", "#ec4899", "fa-palette"),
            ("Inteligencia Artificial", "ai", "#06b6d4", "fa-brain"),
            ("Documentación & Guías", "docs", "#3b82f6", "fa-book-bookmark"),
            ("Finanzas & Negocios", "finance", "#10b981", "fa-money-bill-trend-up"),
            ("Lectura & Artículos", "reading", "#f59e0b", "fa-newspaper"),
            ("Herramientas & Utilidades", "tools", "#6366f1", "fa-screwdriver-wrench"),
            ("Entretenimiento & Videos", "media", "#ef4444", "fa-film")
        ]
        cursor.executemany("""
        INSERT INTO categories (name, slug, color, icon)
        VALUES (?, ?, ?, ?)
        """, default_categories)

    # Default domain settings
    for key, value in DEFAULT_DOMAIN_SETTINGS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value)
        )

    # Performance indexes (safe to create multiple times)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_url ON links(url)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_profile ON links(profile_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_category ON links(category_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_archived ON links(is_archived)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_links_root_domain ON links(root_domain)")

    # Populate root_domain for old/new links that don't have it yet.
    cursor.execute(
        "SELECT value FROM app_settings WHERE key = 'group_subdomains'"
    )
    setting_row = cursor.fetchone()
    group_subdomains = (setting_row[0] != "0") if setting_row else True
    cursor.execute("SELECT id, url, domain FROM links WHERE root_domain IS NULL OR root_domain = ''")
    for row in cursor.fetchall():
        root = get_root_domain(row["domain"] or row["url"], group_subdomains)
        cursor.execute("UPDATE links SET root_domain = ? WHERE id = ?", (root, row["id"]))

    conn.commit()
    conn.close()

# ============================================================
# APPLICATION SETTINGS & DOMAIN NORMALIZATION
# ============================================================
def get_setting(key, default=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO app_settings (key, value, updated_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
    """, (key, str(value)))
    conn.commit()
    conn.close()
    return True

def get_domain_settings():
    result = {}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT key, value FROM app_settings")
        for row in cursor.fetchall():
            result[row["key"]] = row["value"]
    except sqlite3.OperationalError:
        result = {}
    conn.close()
    for key, value in DEFAULT_DOMAIN_SETTINGS.items():
        result.setdefault(key, value)
    result["group_subdomains"] = result["group_subdomains"] != "0"
    result["domain_scan_enabled"] = result["domain_scan_enabled"] != "0"
    result["domain_toast_enabled"] = result["domain_toast_enabled"] != "0"
    try:
        result["domain_scan_interval"] = int(result["domain_scan_interval"])
    except Exception:
        result["domain_scan_interval"] = 10
    try:
        result["domain_min_confidence"] = float(result["domain_min_confidence"])
    except Exception:
        result["domain_min_confidence"] = 0.6
    try:
        result["wordcloud_rotation"] = max(15, int(result.get("wordcloud_rotation", 60)))
    except Exception:
        result["wordcloud_rotation"] = 60
    try:
        result["analytics_retention_days"] = max(7, int(result.get("analytics_retention_days", 90)))
    except Exception:
        result["analytics_retention_days"] = 90
    return result

def set_domain_settings(data):
    mapping = {}
    if "group_subdomains" in data:
        mapping["group_subdomains"] = "1" if data["group_subdomains"] else "0"
    if "domain_scan_enabled" in data:
        mapping["domain_scan_enabled"] = "1" if data["domain_scan_enabled"] else "0"
    if "domain_toast_enabled" in data:
        mapping["domain_toast_enabled"] = "1" if data["domain_toast_enabled"] else "0"
    if "domain_scan_interval" in data:
        try:
            interval = int(data["domain_scan_interval"])
            mapping["domain_scan_interval"] = str(max(0, interval))
        except Exception:
            pass
    if "domain_min_confidence" in data:
        try:
            conf = max(0.0, min(1.0, float(data["domain_min_confidence"])))
            mapping["domain_min_confidence"] = str(conf)
        except Exception:
            pass
    if "wordcloud_rotation" in data:
        try:
            mapping["wordcloud_rotation"] = str(max(15, int(data["wordcloud_rotation"])))
        except Exception:
            pass
    if "analytics_retention_days" in data:
        try:
            mapping["analytics_retention_days"] = str(max(7, int(data["analytics_retention_days"])))
        except Exception:
            pass

    for key, value in mapping.items():
        set_setting(key, value)

    if "group_subdomains" in mapping:
        recompute_root_domains()
    return get_domain_settings()

def recompute_root_domains():
    """Recalculates root_domain for every link after a settings change."""
    group_subdomains = get_domain_settings()["group_subdomains"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, url, domain FROM links")
    rows = cursor.fetchall()
    updated = 0
    for row in rows:
        root = get_root_domain(row["domain"] or row["url"], group_subdomains)
        cursor.execute("UPDATE links SET root_domain = ? WHERE id = ?", (root, row["id"]))
        updated += 1
    # Pending suggestions based on the old grouping are no longer valid.
    cursor.execute("""
    UPDATE domain_suggestions
    SET status = 'superseded', updated_at = datetime('now')
    WHERE status = 'pending'
    """)
    conn.commit()
    conn.close()
    return updated

# ============================================================
# GAMIFICATION ENGINE WITH DECAY & EXTENSIVE EVALUATION
# ============================================================
def get_gamification():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gamification WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        init_db()
        cursor.execute("SELECT * FROM gamification WHERE id = 1")
        row = cursor.fetchone()

    data = dict(row)

    # Decay calculation
    decay_alert = None
    try:
        last_str = data.get("last_active_at")
        if last_str:
            last_active = datetime.fromisoformat(last_str.replace("Z", ""))
            hours_passed = (datetime.now() - last_active).total_seconds() / 3600.0
            if hours_passed >= 24:
                days_inactive = int(hours_passed // 24)
                xp_loss = min(150, days_inactive * 15)
                
                curr_lvl = data["level"]
                lvl_info = next((l for l in LEVELS if l["level"] == curr_lvl), LEVELS[0])
                min_floor = max(0, lvl_info["min_xp"])

                if data["xp"] > min_floor:
                    actual_loss = min(xp_loss, data["xp"] - min_floor)
                    if actual_loss > 0:
                        data["xp"] -= actual_loss
                        decay_alert = {
                            "lost_xp": actual_loss,
                            "days": days_inactive,
                            "message": f"⚠️ Penalización de inactividad: Has perdido {actual_loss} XP por no mantener limpio tu navegador en {days_inactive} días."
                        }
                        cursor.execute("""
                        UPDATE gamification SET xp = ?, last_active_at = datetime('now') WHERE id = 1
                        """, (data["xp"],))
                        conn.commit()
    except Exception:
        pass

    try:
        data["unlocked_trophy_ids"] = json.loads(data["trophies"]) if data["trophies"] else []
    except Exception:
        data["unlocked_trophy_ids"] = []

    all_trophies = []
    for t in TROPHIES_CATALOG:
        t_copy = dict(t)
        t_copy["unlocked"] = t["id"] in data["unlocked_trophy_ids"]
        all_trophies.append(t_copy)

    data["trophies"] = all_trophies
    data["unlocked_count"] = len(data["unlocked_trophy_ids"])
    data["total_trophies"] = len(TROPHIES_CATALOG)
    data["decay_alert"] = decay_alert

    # Next Level calculation
    curr_level = data["level"]
    curr_xp = data["xp"]
    curr_level_info = next((l for l in LEVELS if l["level"] == curr_level), LEVELS[0])
    next_level_info = next((l for l in LEVELS if l["level"] == curr_level + 1), None)

    if next_level_info:
        span = max(1, next_level_info["min_xp"] - curr_level_info["min_xp"])
        progress_xp = curr_xp - curr_level_info["min_xp"]
        pct = max(0, min(100, int((progress_xp / span) * 100)))
        data["next_level_xp"] = next_level_info["min_xp"]
        data["progress_pct"] = pct
    else:
        data["next_level_xp"] = curr_xp
        data["progress_pct"] = 100

    conn.close()
    return data

def add_gamification_event(action, xp_gain=25, meta=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM gamification WHERE id = 1")
    curr = dict(cursor.fetchone())
    try:
        unlocked = json.loads(curr["trophies"]) if curr["trophies"] else []
    except Exception:
        unlocked = []

    new_xp = curr["xp"] + xp_gain
    tabs_closed = curr["tabs_closed"]
    batch_count = curr["batch_count"]
    deleted_count = curr.get("deleted_count", 0)
    updated_count = curr.get("updated_count", 0)

    if action == "open_link":
        tabs_closed += 1
    elif action == "batch_import":
        batch_count += 1
    elif action == "delete_link":
        deleted_count += 1
    elif action == "update_link":
        updated_count += 1

    # Gather data for trophy checks
    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0")
    total_active_links = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_read = 1")
    read_count = cursor.fetchone()[0]

    cursor.execute("SELECT credentials, sublinks FROM links WHERE is_archived = 0")
    all_links_rows = cursor.fetchall()
    total_credentials_count = 0
    max_sublinks_on_single = 0
    for r in all_links_rows:
        try:
            creds = json.loads(r[0]) if r[0] else []
            total_credentials_count += len(creds)
        except Exception:
            pass
        try:
            subs = json.loads(r[1]) if r[1] else []
            if len(subs) > max_sublinks_on_single:
                max_sublinks_on_single = len(subs)
        except Exception:
            pass

    # Category counts
    cursor.execute("""
    SELECT c.slug, COUNT(l.id) as cnt
    FROM categories c
    LEFT JOIN links l ON c.id = l.category_id AND l.is_archived = 0
    GROUP BY c.id
    """)
    cat_counts = {r[0]: r[1] for r in cursor.fetchall()}

    # Profile counts
    cursor.execute("""
    SELECT p.slug, COUNT(l.id) as cnt
    FROM profiles p
    LEFT JOIN links l ON p.id = l.profile_id AND l.is_archived = 0
    GROUP BY p.id
    """)
    prof_counts = {r[0]: r[1] for r in cursor.fetchall()}

    active_cats = sum(1 for c, cnt in cat_counts.items() if cnt > 0)
    ram_saved_mb = total_active_links * 220

    new_trophies = []
    def award(trophy_id):
        if trophy_id not in unlocked:
            unlocked.append(trophy_id)
            obj = next((t for t in TROPHIES_CATALOG if t["id"] == trophy_id), None)
            if obj:
                new_trophies.append(obj)

    # General Trophies
    if total_active_links >= 1: award("first_link")
    if tabs_closed >= 1: award("tab_closed")
    if batch_count >= 1: award("batch_saver")
    if ram_saved_mb >= 1500: award("ram_hero")
    if ram_saved_mb >= 3000: award("ram_titan")
    if total_active_links >= 15: award("zen_collector")
    if read_count >= 4: award("bookworm")

    # Cleaning, Credentials & Sublinks
    if deleted_count >= 1: award("clean_pruner")
    if deleted_count >= 5: award("deep_cleaner")
    if updated_count >= 1: award("renovator")
    if action == "complete_link": award("link_perfectionist")
    if total_credentials_count >= 1: award("vault_master")
    if max_sublinks_on_single >= 3: award("sublink_architect")

    # Profile Trophies
    if prof_counts.get("personal", 0) >= 3: award("prof_personal")
    if prof_counts.get("trabajo", 0) >= 3: award("prof_work")
    if prof_counts.get("estudio", 0) >= 3: award("prof_study")
    if prof_counts.get("dev", 0) >= 3: award("prof_dev")
    if action in ["add_profile", "custom_profile"]: award("prof_creator")

    # Category / Topic Trophies
    if cat_counts.get("dev", 0) >= 1: award("cat_code")
    if cat_counts.get("design", 0) >= 1: award("cat_design")
    if cat_counts.get("ai", 0) >= 1: award("cat_ai")
    if cat_counts.get("docs", 0) >= 1: award("cat_docs")
    if cat_counts.get("finance", 0) >= 1: award("cat_finance")
    if cat_counts.get("reading", 0) >= 1: award("cat_reading")
    if cat_counts.get("tools", 0) >= 1: award("cat_tools")
    if cat_counts.get("media", 0) >= 1: award("cat_media")
    if active_cats >= 5: award("polymath")

    # Trophy bonus XP
    for nt in new_trophies:
        new_xp += nt["xp"]

    current_level = 1
    current_title = LEVELS[0]["title"]
    for lvl in LEVELS:
        if new_xp >= lvl["min_xp"]:
            current_level = lvl["level"]
            current_title = lvl["title"]

    level_up = current_level > curr["level"]
    if current_level >= 4: award("platinum_zero")
    if current_level >= 7 and len(unlocked) >= 12: award("diamond_immortal")

    cursor.execute("""
    UPDATE gamification
    SET xp = ?, level = ?, level_title = ?, trophies = ?,
        tabs_closed = ?, batch_count = ?, deleted_count = ?, updated_count = ?,
        last_active_at = datetime('now'), updated_at = datetime('now')
    WHERE id = 1
    """, (new_xp, current_level, current_title, json.dumps(unlocked),
          tabs_closed, batch_count, deleted_count, updated_count))

    conn.commit()
    conn.close()

    return {
        "xp": new_xp,
        "xp_gained": xp_gain,
        "level": current_level,
        "level_title": current_title,
        "level_up": level_up,
        "new_trophies": new_trophies
    }

# ============================================================
# CRUD FOR LINKS WITH CREDENTIALS, SUBLINKS & PRUNING
# ============================================================
def _normalize_credentials(credentials):
    """Guarantees every account has a stable id and consistent fields."""
    if not isinstance(credentials, list):
        return []
    normalized = []
    for idx, cred in enumerate(credentials):
        if not isinstance(cred, dict):
            continue
        label = str(cred.get("label", "") or "").strip() or f"Cuenta {idx + 1}"
        username = str(cred.get("username", "") or "").strip()
        password = str(cred.get("password", "") or "")
        notes = str(cred.get("notes", "") or "").strip()
        if not (username or password or notes):
            continue
        normalized.append({
            "id": str(cred.get("id") or f"cred_{int(time.time() * 1000)}_{idx}"),
            "label": label,
            "username": username,
            "password": password,
            "notes": notes,
            "created_at": cred.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return normalized

def _normalize_sublinks(sublinks):
    if not isinstance(sublinks, list):
        return []
    normalized = []
    for idx, sub in enumerate(sublinks):
        if not isinstance(sub, dict):
            continue
        url = str(sub.get("url", "") or "").strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        normalized.append({
            "id": str(sub.get("id") or f"sub_{int(time.time() * 1000)}_{idx}"),
            "title": str(sub.get("title", "") or "").strip() or url,
            "url": url,
            "is_read": 1 if sub.get("is_read") in (1, True, "1") else 0,
            "created_at": sub.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return normalized

def _format_link_dict(r):
    res = dict(r)
    for field in ['tags', 'credentials', 'sublinks']:
        try:
            res[field] = json.loads(res[field]) if res.get(field) else []
        except Exception:
            res[field] = []
    res["credentials"] = _normalize_credentials(res.get("credentials"))
    res["sublinks"] = _normalize_sublinks(res.get("sublinks"))
    return res

def get_all_links(profile_id=None, category_id=None, query=None, favorite_only=False,
                  unread_only=False, archived=False, root_domain=None):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
    SELECT l.*, c.name as category_name, c.color as category_color,
           p.name as profile_name, p.color as profile_color
    FROM links l
    LEFT JOIN categories c ON l.category_id = c.id
    LEFT JOIN profiles p ON l.profile_id = p.id
    WHERE l.is_archived = ?
    """
    params = [1 if archived else 0]

    if profile_id:
        sql += " AND l.profile_id = ?"
        params.append(profile_id)

    if category_id:
        sql += " AND l.category_id = ?"
        params.append(category_id)

    if root_domain:
        sql += " AND l.root_domain = ?"
        params.append(root_domain)

    if favorite_only:
        sql += " AND l.is_favorite = 1"

    if unread_only:
        sql += " AND l.is_read = 0"

    if query:
        sql += " AND (l.title LIKE ? OR l.description LIKE ? OR l.url LIKE ? OR l.domain LIKE ? OR l.tags LIKE ? OR l.notes LIKE ?)"
        q = f"%{query}%"
        params.extend([q, q, q, q, q, q])

    sql += " ORDER BY l.id DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    results = [_format_link_dict(r) for r in rows]
    conn.close()
    return results

def get_link_by_id(link_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT l.*, c.name as category_name, c.color as category_color,
           p.name as profile_name, p.color as profile_color
    FROM links l
    LEFT JOIN categories c ON l.category_id = c.id
    LEFT JOIN profiles p ON l.profile_id = p.id
    WHERE l.id = ?
    """, (link_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _format_link_dict(row)
    return None

def is_link_complete(title, description, thumbnail_url, tags, notes):
    has_title = bool(title and len(title.strip()) > 3)
    has_desc = bool(description and len(description.strip()) > 10)
    has_thumb = bool(thumbnail_url and len(thumbnail_url.strip()) > 5)
    has_tags = bool(tags and len(tags) > 0)
    has_notes = bool(notes and len(notes.strip()) > 3)
    return has_title and has_desc and has_thumb and has_tags and has_notes

def add_link(url, title, description="", thumbnail_url="", favicon_url="", domain="",
             category_id=None, profile_id=None, tags=None, credentials=None, sublinks=None, notes=""):
    conn = get_connection()
    cursor = conn.cursor()
    tags_json = json.dumps(tags if isinstance(tags, list) else [])
    creds_json = json.dumps(_normalize_credentials(credentials))
    subs_json = json.dumps(_normalize_sublinks(sublinks))
    root_domain = get_root_domain(domain or url, get_domain_settings()["group_subdomains"])

    if not profile_id:
        cursor.execute("SELECT id FROM profiles WHERE is_default = 1 LIMIT 1")
        row = cursor.fetchone()
        profile_id = row[0] if row else 1

    cursor.execute("""
    INSERT INTO links (url, title, description, thumbnail_url, favicon_url, domain,
                       root_domain, category_id, profile_id, tags, credentials, sublinks, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (url, title, description, thumbnail_url, favicon_url, domain,
          root_domain, category_id, profile_id, tags_json, creds_json, subs_json, notes))
    link_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Create automatic backup for safety
    create_auto_backup("add")

    # Gamification
    xp = 30
    action = "add_link"
    if is_link_complete(title, description, thumbnail_url, tags, notes):
        xp += 40
        action = "complete_link"

    gami = add_gamification_event(action, xp_gain=xp)
    res = get_link_by_id(link_id)
    if res:
        res["_gamification"] = gami
    return res

def update_link(link_id, **kwargs):
    conn = get_connection()
    cursor = conn.cursor()
    valid_fields = ['url', 'title', 'description', 'thumbnail_url', 'favicon_url',
                    'domain', 'category_id', 'profile_id', 'tags', 'credentials',
                    'sublinks', 'is_favorite', 'is_read', 'is_archived', 'visit_count', 'notes']
    
    updates = []
    params = []
    for k, v in kwargs.items():
        if k in valid_fields:
            updates.append(f"{k} = ?")
            if k == 'credentials':
                params.append(json.dumps(_normalize_credentials(v)))
            elif k == 'sublinks':
                params.append(json.dumps(_normalize_sublinks(v)))
            elif k == 'tags' and isinstance(v, (list, dict)):
                params.append(json.dumps(v))
            else:
                params.append(v)

    if 'url' in kwargs or 'domain' in kwargs:
        base_domain = kwargs.get('domain')
        if not base_domain:
            cursor.execute("SELECT domain FROM links WHERE id = ?", (link_id,))
            current = cursor.fetchone()
            base_domain = current[0] if current else ''
        root_domain = get_root_domain(
            base_domain or kwargs.get('url', ''),
            get_domain_settings()["group_subdomains"]
        )
        updates.append("root_domain = ?")
        params.append(root_domain)
    
    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(link_id)
        sql = f"UPDATE links SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, params)
        conn.commit()
    
    conn.close()

    gami = None
    if kwargs.get('is_read') == 1:
        gami = add_gamification_event("mark_read", xp_gain=20)
    elif any(k in kwargs for k in ['title', 'notes', 'tags', 'credentials', 'sublinks', 'category_id', 'profile_id']):
        gami = add_gamification_event("update_link", xp_gain=25)

    res = get_link_by_id(link_id)
    if res and gami:
        res["_gamification"] = gami
    return res

def delete_link(link_id):
    # Safety snapshot before deletion
    create_auto_backup("pre_delete")

    conn = get_connection()
    cursor = conn.cursor()
    # If this link was the main target of a previous merge, restore its
    # archived siblings instead of leaving them orphaned/invisible.
    cursor.execute(
        "UPDATE links SET is_archived = 0, merged_into_id = NULL WHERE merged_into_id = ?",
        (link_id,)
    )
    cursor.execute("DELETE FROM links WHERE id = ?", (link_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    gami = None
    if affected > 0:
        gami = add_gamification_event("delete_link", xp_gain=25)

    return {"success": affected > 0, "_gamification": gami}

# ============================================================
# MULTI-ACCOUNT CREDENTIALS MANAGEMENT PER LINK
# ============================================================
def add_credential_to_link(link_id, label, username, password, notes=""):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    creds = link.get("credentials", [])
    cred_id = f"cred_{int(time.time() * 1000)}_{len(creds) + 1}"
    new_cred = {
        "id": cred_id,
        "label": label.strip() or "Cuenta",
        "username": username.strip(),
        "password": password.strip(),
        "notes": notes.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    creds.append(new_cred)
    update_link(link_id, credentials=creds)
    gami = add_gamification_event("add_credential", xp_gain=30)
    return {"credential": new_cred, "all_credentials": creds, "_gamification": gami}

def update_credential_in_link(link_id, cred_id, label, username, password, notes=""):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    creds = link.get("credentials", [])
    found = False
    for c in creds:
        if c.get("id") == cred_id:
            c["label"] = label.strip() or c["label"]
            c["username"] = username.strip()
            c["password"] = password.strip()
            c["notes"] = notes.strip()
            found = True
            break
    
    if found:
        update_link(link_id, credentials=creds)
    return {"success": found, "all_credentials": creds}

def delete_credential_from_link(link_id, cred_id):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    creds = [c for c in link.get("credentials", []) if c.get("id") != cred_id]
    update_link(link_id, credentials=creds)
    return {"success": True, "all_credentials": creds}

# ============================================================
# ASSOCIATED TABS / SUBLINKS PER LINK (CHILD TABS SUBMODAL)
# ============================================================
def add_sublink_to_link(link_id, title, url):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    sublinks = link.get("sublinks", [])
    sub_id = f"sub_{int(time.time() * 1000)}_{len(sublinks) + 1}"
    new_sub = {
        "id": sub_id,
        "title": title.strip() or url.strip(),
        "url": url.strip(),
        "is_read": 0,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    sublinks.append(new_sub)
    update_link(link_id, sublinks=sublinks)
    gami = add_gamification_event("add_sublink", xp_gain=20)
    return {"sublink": new_sub, "all_sublinks": sublinks, "_gamification": gami}

def batch_add_sublinks(link_id, urls_text):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    sublinks = link.get("sublinks", [])
    lines = [line.strip() for line in urls_text.splitlines() if line.strip()]
    added = []

    for idx, u in enumerate(lines):
        clean_u = u if u.startswith(('http://', 'https://')) else f"https://{u}"
        sub_id = f"sub_{int(time.time() * 1000)}_{len(sublinks) + idx + 1}"
        item = {
            "id": sub_id,
            "title": clean_u.split('/')[-1] or link.get("title", clean_u),
            "url": clean_u,
            "is_read": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        sublinks.append(item)
        added.append(item)

    update_link(link_id, sublinks=sublinks)
    gami = add_gamification_event("batch_sublinks", xp_gain=len(added) * 15 + 30)
    return {"added_count": len(added), "all_sublinks": sublinks, "_gamification": gami}

def toggle_sublink_read(link_id, sub_id):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    sublinks = link.get("sublinks", [])
    for s in sublinks:
        if s.get("id") == sub_id:
            s["is_read"] = 0 if s.get("is_read") == 1 else 1
            break
    
    update_link(link_id, sublinks=sublinks)
    return {"all_sublinks": sublinks}

def delete_sublink_from_link(link_id, sub_id):
    link = get_link_by_id(link_id)
    if not link:
        return None
    
    sublinks = [s for s in link.get("sublinks", []) if s.get("id") != sub_id]
    update_link(link_id, sublinks=sublinks)
    return {"success": True, "all_sublinks": sublinks}

# ============================================================
# EXPORT / IMPORT ENGINE (ABSOLUTE DATA PROTECTION)
# ============================================================
def export_database_json():
    """Generates a complete portable JSON backup."""
    conn = get_connection()
    cursor = conn.cursor()

    # Profiles
    cursor.execute("SELECT * FROM profiles")
    profiles = [dict(r) for r in cursor.fetchall()]

    # Categories
    cursor.execute("SELECT * FROM categories")
    categories = [dict(r) for r in cursor.fetchall()]

    # Links
    cursor.execute("SELECT * FROM links")
    raw_links = [dict(r) for r in cursor.fetchall()]
    links = []
    for l in raw_links:
        for f in ['tags', 'credentials', 'sublinks']:
            try:
                l[f] = json.loads(l[f]) if l.get(f) else []
            except Exception:
                l[f] = []
        links.append(l)

    # Gamification
    cursor.execute("SELECT * FROM gamification WHERE id = 1")
    gami_row = cursor.fetchone()
    gami = dict(gami_row) if gami_row else {"xp": 0, "level": 1, "level_title": "", "trophies": []}
    try:
        gami["trophies"] = json.loads(gami["trophies"]) if gami.get("trophies") else []
    except Exception:
        gami["trophies"] = []

    # Persistent assistant conversations
    cursor.execute("SELECT * FROM chat_sessions ORDER BY id ASC")
    chat_sessions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM chat_messages ORDER BY id ASC")
    chat_messages = []
    for m in cursor.fetchall():
        item = dict(m)
        try:
            item["data"] = json.loads(item["data"]) if item.get("data") else {}
        except Exception:
            item["data"] = {}
        chat_messages.append(item)

    conn.close()

    return {
        "app": "Pageneitor",
        "version": "3.9",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "profiles": profiles,
        "categories": categories,
        "links": links,
        "gamification": gami,
        "chat_sessions": chat_sessions,
        "chat_messages": chat_messages
    }

def import_database_json(data, mode="merge"):
    """
    Imports portable JSON backup.
    mode='merge': preserves existing items, appends non-existent ones.
    mode='replace': completely restores database.
    """
    # 1. Take safety snapshot of current DB first!
    create_auto_backup("pre_import_json")

    conn = get_connection()
    cursor = conn.cursor()

    if mode == "replace":
        cursor.execute("DELETE FROM chat_messages")
        cursor.execute("DELETE FROM chat_sessions")
        cursor.execute("DELETE FROM domain_suggestions")
        cursor.execute("DELETE FROM domain_action_log")
        cursor.execute("DELETE FROM links")
        cursor.execute("DELETE FROM categories")
        cursor.execute("DELETE FROM profiles")

    # Import Profiles
    profile_map = {} # old_id -> new_id
    for p in data.get("profiles", []):
        name = p.get("name")
        cursor.execute("SELECT id FROM profiles WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            profile_map[p.get("id")] = row[0]
        else:
            slug = p.get("slug") or name.lower().replace(" ", "-")
            cursor.execute("""
            INSERT INTO profiles (name, slug, color, icon, description, is_default)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (name, slug, p.get("color", "#3b82f6"), p.get("icon", "fa-user"), p.get("description", ""), p.get("is_default", 0)))
            profile_map[p.get("id")] = cursor.lastrowid

    # Import Categories
    category_map = {} # old_id -> new_id
    for c in data.get("categories", []):
        name = c.get("name")
        cursor.execute("SELECT id FROM categories WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            category_map[c.get("id")] = row[0]
        else:
            slug = c.get("slug") or name.lower().replace(" ", "-")
            cursor.execute("""
            INSERT INTO categories (name, slug, color, icon)
            VALUES (?, ?, ?, ?)
            """, (name, slug, c.get("color", "#8b5cf6"), c.get("icon", "fa-folder")))
            category_map[c.get("id")] = cursor.lastrowid

    # Import Links
    imported_links_count = 0
    for l in data.get("links", []):
        url = l.get("url")
        # Check if exists in merge mode
        if mode == "merge":
            cursor.execute("SELECT id FROM links WHERE url = ?", (url,))
            if cursor.fetchone():
                continue

        p_id = profile_map.get(l.get("profile_id"))
        c_id = category_map.get(l.get("category_id"))

        tags_json = json.dumps(l.get("tags", []) if isinstance(l.get("tags"), list) else [])
        creds_json = json.dumps(_normalize_credentials(l.get("credentials")))
        subs_json = json.dumps(_normalize_sublinks(l.get("sublinks")))

        cursor.execute("""
        INSERT INTO links (url, title, description, thumbnail_url, favicon_url, domain,
                           category_id, profile_id, tags, credentials, sublinks, notes,
                           is_favorite, is_read, is_archived, visit_count,
                           created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url, l.get("title", url), l.get("description", ""), l.get("thumbnail_url", ""),
            l.get("favicon_url", ""), l.get("domain", ""), c_id, p_id,
            tags_json, creds_json, subs_json, l.get("notes", ""),
            l.get("is_favorite", 0), l.get("is_read", 0), l.get("is_archived", 0),
            l.get("visit_count", 0),
            l.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            l.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        imported_links_count += 1

    # Import persistent chat conversations
    imported_chat_sessions = 0
    imported_chat_messages = 0
    session_map = {}
    messages_by_session = {}
    for m in data.get("chat_messages", []):
        messages_by_session.setdefault(m.get("session_id"), []).append(m)

    for s in data.get("chat_sessions", []):
        title = (s.get("title") or "Nueva conversación").strip()[:90]
        created = s.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = s.get("updated_at") or created
        existing = None
        if mode == "merge":
            cursor.execute(
                "SELECT id FROM chat_sessions WHERE title = ? AND created_at = ?",
                (title, created)
            )
            existing = cursor.fetchone()
        if existing:
            sid = existing[0]
        else:
            cursor.execute(
                "INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
                (title, created, updated)
            )
            sid = cursor.lastrowid
            imported_chat_sessions += 1
        session_map[s.get("id")] = sid

    for old_sid, messages in messages_by_session.items():
        new_sid = session_map.get(old_sid)
        if not new_sid:
            continue
        for m in messages:
            role = m.get("role") or "assistant"
            content = m.get("content") or ""
            created = m.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if mode == "merge":
                cursor.execute("""
                SELECT id FROM chat_messages
                WHERE session_id = ? AND role = ? AND content = ? AND created_at = ?
                """, (new_sid, role, content, created))
                if cursor.fetchone():
                    continue
            msg_data = m.get("data") if isinstance(m.get("data"), dict) else {}
            cursor.execute("""
            INSERT INTO chat_messages (session_id, role, content, data, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (new_sid, role, content, json.dumps(msg_data, ensure_ascii=False), created))
            imported_chat_messages += 1

    # Merge or restore gamification
    gami_data = data.get("gamification")
    if gami_data:
        if mode == "replace":
            cursor.execute("""
            UPDATE gamification
            SET xp = ?, level = ?, level_title = ?, trophies = ?, tabs_closed = ?
            WHERE id = 1
            """, (
                gami_data.get("xp", 80), gami_data.get("level", 1),
                gami_data.get("level_title", "Acumulador en Terapia"),
                json.dumps(gami_data.get("trophies", [])),
                gami_data.get("tabs_closed", 0)
            ))
        else:
            # Add bonus XP from import
            cursor.execute("UPDATE gamification SET xp = xp + ? WHERE id = 1", (imported_links_count * 20,))

    conn.commit()
    conn.close()

    # Root domains are recalculated after JSON import so grouping works
    # immediately, including subdomains and custom settings.
    recompute_root_domains()

    return {
        "success": True,
        "imported_links": imported_links_count,
        "imported_chat_sessions": imported_chat_sessions,
        "imported_chat_messages": imported_chat_messages,
        "mode": mode
    }

def restore_database_from_file(uploaded_file_path):
    """Restores database from an external .db SQLite file safely."""
    if not os.path.exists(uploaded_file_path):
        return False, "El archivo de base de datos no existe."

    if os.path.abspath(uploaded_file_path) == os.path.abspath(DB_PATH):
        return False, "El archivo seleccionado ya es la base de datos activa."

    # Validate that it is a valid SQLite DB
    try:
        test_conn = sqlite3.connect(uploaded_file_path)
        test_cursor = test_conn.cursor()
        test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in test_cursor.fetchall()]
        test_conn.close()
        if "links" not in tables:
            return False, "El archivo seleccionado no es una base de datos válida de Pageneitor."
    except Exception as e:
        return False, f"Error validando archivo: {e}"

    # Safety auto-backup before replacement!
    create_auto_backup("pre_restore_file")

    try:
        # Copy through SQLite (never raw shutil.copy2) so WAL state and
        # partially written pages cannot corrupt the restored database.
        src = sqlite3.connect(uploaded_file_path)
        dst = sqlite3.connect(DB_PATH)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()

        # Re-run migrations to ensure compatibility with this version.
        init_db()
        return True, "Base de datos restaurada con éxito."
    except Exception as e:
        return False, f"Error al restaurar: {e}"

def create_manual_backup():
    """Creates a backup that is never auto-pruned."""
    path = create_auto_backup("manual")
    if path:
        create_auto_backup("pre_manual")
    return path

# ============================================================
# PROFILES & CATEGORIES CRUD
# ============================================================
def get_profiles():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.*, COUNT(l.id) as link_count
    FROM profiles p
    LEFT JOIN links l ON p.id = l.profile_id AND l.is_archived = 0
    GROUP BY p.id
    ORDER BY p.id ASC
    """)
    rows = cursor.fetchall()
    res = [dict(r) for r in rows]
    conn.close()
    return res

def add_profile(name, color="#3b82f6", icon="fa-user", description=""):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, color FROM profiles WHERE name = ?", (name,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {"id": existing[0], "name": existing[1], "color": existing[2], "_gamification": None}

    slug = name.lower().replace(" ", "-").replace("/", "")
    cursor.execute("SELECT COUNT(*) FROM profiles WHERE slug = ?", (slug,))
    if cursor.fetchone()[0] > 0:
        slug = f"{slug}-{int(time.time())}"

    cursor.execute("""
    INSERT INTO profiles (name, slug, color, icon, description)
    VALUES (?, ?, ?, ?, ?)
    """, (name, slug, color, icon, description))
    pid = cursor.lastrowid
    conn.commit()
    conn.close()
    gami = add_gamification_event("add_profile", xp_gain=50)
    return {"id": pid, "name": name, "color": color, "_gamification": gami}

def update_profile(profile_id, name, color=None, icon=None, description=None):
    conn = get_connection()
    cursor = conn.cursor()
    updates = ["name = ?"]
    params = [name]

    if color:
        updates.append("color = ?")
        params.append(color)
    if icon:
        updates.append("icon = ?")
        params.append(icon)
    if description is not None:
        updates.append("description = ?")
        params.append(description)

    params.append(profile_id)
    cursor.execute(f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"id": profile_id, "name": name, "color": color}

def delete_profile(profile_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE links SET profile_id = NULL WHERE profile_id = ?", (profile_id,))
    cursor.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_categories():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT c.*, COUNT(l.id) as link_count
    FROM categories c
    LEFT JOIN links l ON c.id = l.category_id AND l.is_archived = 0
    GROUP BY c.id
    ORDER BY c.id ASC
    """)
    rows = cursor.fetchall()
    res = [dict(r) for r in rows]
    conn.close()
    return res

def add_category(name, color="#8b5cf6", icon="fa-folder"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, color FROM categories WHERE name = ?", (name,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return {"id": existing[0], "name": existing[1], "color": existing[2], "_gamification": None}

    slug = name.lower().replace(" ", "-").replace("/", "")
    cursor.execute("SELECT COUNT(*) FROM categories WHERE slug = ?", (slug,))
    if cursor.fetchone()[0] > 0:
        slug = f"{slug}-{int(time.time())}"

    cursor.execute("""
    INSERT INTO categories (name, slug, color, icon)
    VALUES (?, ?, ?, ?)
    """, (name, slug, color, icon))
    cid = cursor.lastrowid
    conn.commit()
    conn.close()
    gami = add_gamification_event("add_category", xp_gain=50)
    return {"id": cid, "name": name, "color": color, "_gamification": gami}

def update_category(category_id, name, color=None, icon=None):
    conn = get_connection()
    cursor = conn.cursor()
    updates = ["name = ?"]
    params = [name]

    if color:
        updates.append("color = ?")
        params.append(color)
    if icon:
        updates.append("icon = ?")
        params.append(icon)

    params.append(category_id)
    cursor.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"id": category_id, "name": name, "color": color}

def delete_category(category_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE links SET category_id = NULL WHERE category_id = ?", (category_id,))
    cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ============================================================
# PERSISTENT CHAT ASSISTANT SESSIONS
# ============================================================
def _chat_message_to_dict(row):
    item = dict(row)
    try:
        item["data"] = json.loads(item["data"]) if item.get("data") else {}
    except Exception:
        item["data"] = {}
    return item

def create_chat_session(title=None):
    conn = get_connection()
    cursor = conn.cursor()
    clean_title = (title or "Nueva conversación").strip()[:90] or "Nueva conversación"
    cursor.execute(
        "INSERT INTO chat_sessions (title) VALUES (?)",
        (clean_title,)
    )
    sid = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": sid, "title": clean_title}

def get_chat_sessions(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.*,
           (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count,
           (SELECT m.content FROM chat_messages m
             WHERE m.session_id = s.id ORDER BY m.id DESC LIMIT 1) AS last_message
    FROM chat_sessions s
    ORDER BY s.updated_at DESC, s.id DESC
    LIMIT ?
    """, (int(limit),))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_chat_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    session = dict(row)
    cursor.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    )
    session["messages"] = [_chat_message_to_dict(m) for m in cursor.fetchall()]
    conn.close()
    return session

def add_chat_message(session_id, role, content, data=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM chat_sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        return None

    # First user message becomes the conversation title.
    if role == "user":
        cursor.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'user'",
            (session_id,)
        )
        if cursor.fetchone()[0] == 0:
            title = (content or "Nueva conversación").strip().replace("\n", " ")[:70]
            if title:
                cursor.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))

    data_json = json.dumps(data or {}, ensure_ascii=False)
    cursor.execute("""
    INSERT INTO chat_messages (session_id, role, content, data)
    VALUES (?, ?, ?, ?)
    """, (session_id, role, content, data_json))
    mid = cursor.lastrowid
    cursor.execute(
        "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?",
        (session_id,)
    )
    cursor.execute("SELECT * FROM chat_messages WHERE id = ?", (mid,))
    saved = _chat_message_to_dict(cursor.fetchone())
    conn.commit()
    conn.close()
    return saved

def rename_chat_session(session_id, title):
    clean_title = (title or "").strip()[:90]
    if not clean_title:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (clean_title, session_id)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def delete_chat_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def clear_chat_sessions():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages")
    cursor.execute("DELETE FROM chat_sessions")
    conn.commit()
    conn.close()
    return True

# ============================================================
# LOCAL TELEMETRY & LLM CACHE
# ============================================================
def log_analytics_event(event_type, action="", entity_type="", entity_id="",
                        metadata=None, session_id=""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO analytics_events
            (event_type, action, entity_type, entity_id, metadata, session_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(event_type)[:80],
            str(action)[:80],
            str(entity_type)[:80],
            str(entity_id)[:120],
            json.dumps(metadata or {}, ensure_ascii=False)[:8000],
            str(session_id or "")[:120],
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Analytics] Could not persist event: {e}")
        return False

def get_analytics_events(limit=500, event_type=None):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM analytics_events"
    params = []
    if event_type:
        sql += " WHERE event_type = ?"
        params.append(event_type)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    cursor.execute(sql, params)
    rows = []
    for row in cursor.fetchall():
        item = dict(row)
        try:
            item["metadata"] = json.loads(item["metadata"]) if item.get("metadata") else {}
        except Exception:
            item["metadata"] = {}
        rows.append(item)
    conn.close()
    return rows

def prune_analytics_events(days=90, max_events=50000):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM analytics_events WHERE created_at < datetime('now', ?)",
        (f"-{max(1, int(days))} days",)
    )
    cursor.execute("SELECT COUNT(*) FROM analytics_events")
    total = cursor.fetchone()[0]
    if total > max_events:
        cursor.execute("""
        DELETE FROM analytics_events
        WHERE id IN (
            SELECT id FROM analytics_events ORDER BY id ASC LIMIT ?
        )
        """, (total - int(max_events),))
    conn.commit()
    conn.close()
    return True

def get_llm_cache(key):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM llm_cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    try:
        item["payload"] = json.loads(item["payload"]) if item.get("payload") else {}
    except Exception:
        item["payload"] = {}
    return item

def set_llm_cache(key, kind, payload):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO llm_cache (key, kind, payload, updated_at)
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT(key) DO UPDATE SET
        kind = excluded.kind,
        payload = excluded.payload,
        updated_at = datetime('now')
    """, (key, kind, json.dumps(payload or {}, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return True

def invalidate_llm_cache(key=None, kind=None):
    conn = get_connection()
    cursor = conn.cursor()
    if key:
        cursor.execute("DELETE FROM llm_cache WHERE key = ?", (key,))
    elif kind:
        cursor.execute("DELETE FROM llm_cache WHERE kind = ?", (kind,))
    else:
        cursor.execute("DELETE FROM llm_cache")
    conn.commit()
    conn.close()
    return True

# ============================================================
# DOMAIN GROUPS, SUGGESTIONS, MERGE & UNDO
# ============================================================
def _suggestion_to_dict(row):
    item = dict(row)
    try:
        item["payload"] = json.loads(item["payload"]) if item.get("payload") else {}
    except Exception:
        item["payload"] = {}
    return item

def get_domain_groups(include_archived=False):
    links = get_all_links(archived=include_archived)
    groups = {}
    for link in links:
        root = link.get("root_domain") or get_root_domain(
            link.get("domain") or link.get("url", ""),
            get_domain_settings()["group_subdomains"]
        )
        if not root:
            root = "sin-dominio"
        groups.setdefault(root, []).append(link)

    result = []
    for root, items in groups.items():
        items.sort(key=lambda l: (
            -(l.get("is_favorite") or 0),
            -(l.get("visit_count") or 0),
            -(l.get("id") or 0),
        ))
        thumbnails = [
            item.get("thumbnail_url") for item in items
            if item.get("thumbnail_url")
        ][:4]
        result.append({
            "root_domain": root,
            "count": len(items),
            "thumbnails": thumbnails,
            "links": items,
        })

    result.sort(key=lambda g: (-g["count"], g["root_domain"]))
    return result

def get_domain_group(root_domain):
    for group in get_domain_groups():
        if group["root_domain"] == root_domain:
            return group
    return None

def create_domain_suggestion(root_domain, action, payload, reason="", confidence=0.0, signature=None):
    if not root_domain:
        return None
    payload = payload or {}
    if not signature:
        seed = json.dumps(
            {"root": root_domain, "action": action, "payload": payload},
            sort_keys=True, ensure_ascii=False
        )
        signature = hashlib.sha1(seed.encode("utf-8")).hexdigest()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id FROM domain_suggestions
    WHERE root_domain = ? AND action = ? AND signature = ? AND status = 'pending'
    LIMIT 1
    """, (root_domain, action, signature))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
        UPDATE domain_suggestions
        SET payload = ?, reason = ?, confidence = ?, updated_at = datetime('now')
        WHERE id = ?
        """, (
            json.dumps(payload, ensure_ascii=False),
            reason,
            float(confidence or 0),
            existing[0],
        ))
        sid = existing[0]
    else:
        # A newer analysis replaces the previous pending proposal for the
        # same domain/action instead of accumulating duplicates.
        cursor.execute("""
        UPDATE domain_suggestions
        SET status = 'superseded', updated_at = datetime('now')
        WHERE root_domain = ? AND action = ? AND status = 'pending'
        """, (root_domain, action))
        cursor.execute("""
        INSERT INTO domain_suggestions
            (root_domain, action, payload, reason, confidence, signature)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            root_domain, action,
            json.dumps(payload, ensure_ascii=False),
            reason, float(confidence or 0), signature
        ))
        sid = cursor.lastrowid

    cursor.execute("SELECT * FROM domain_suggestions WHERE id = ?", (sid,))
    result = _suggestion_to_dict(cursor.fetchone())
    conn.commit()
    conn.close()
    return result

def get_domain_suggestions(status=None, unread_only=False, limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM domain_suggestions WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if unread_only:
        sql += " AND is_read = 0 AND status = 'pending'"
    sql += " ORDER BY is_read ASC, updated_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    cursor.execute(sql, params)
    rows = [_suggestion_to_dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_domain_suggestion(suggestion_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM domain_suggestions WHERE id = ?", (suggestion_id,))
    row = cursor.fetchone()
    conn.close()
    return _suggestion_to_dict(row) if row else None

def count_pending_domain_suggestions():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM domain_suggestions WHERE status = 'pending'")
    count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM domain_suggestions WHERE status = 'pending' AND is_read = 0")
    unread = cursor.fetchone()[0]
    conn.close()
    return {"pending": count, "unread": unread}

def mark_domain_suggestions_read(suggestion_ids=None):
    conn = get_connection()
    cursor = conn.cursor()
    if suggestion_ids:
        placeholders = ",".join("?" for _ in suggestion_ids)
        cursor.execute(
            f"UPDATE domain_suggestions SET is_read = 1 WHERE id IN ({placeholders})",
            list(suggestion_ids)
        )
    else:
        cursor.execute("UPDATE domain_suggestions SET is_read = 1 WHERE status = 'pending'")
    conn.commit()
    conn.close()
    return True

def set_domain_suggestion_status(suggestion_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE domain_suggestions
    SET status = ?, is_read = 1,
        applied_at = CASE WHEN ? = 'applied' THEN datetime('now') ELSE applied_at END,
        updated_at = datetime('now')
    WHERE id = ?
    """, (status, status, suggestion_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def _domain_log_action(action, root_domain, before, after, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO domain_action_log
        (action, root_domain, payload_before, payload_after, description)
    VALUES (?, ?, ?, ?, ?)
    """, (
        action, root_domain,
        json.dumps(before or {}, ensure_ascii=False),
        json.dumps(after or {}, ensure_ascii=False),
        description or "",
    ))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_domain_action_log(limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM domain_action_log ORDER BY id DESC LIMIT ?",
        (int(limit),)
    )
    rows = []
    for r in cursor.fetchall():
        item = dict(r)
        for key in ("payload_before", "payload_after"):
            try:
                item[key] = json.loads(item[key]) if item.get(key) else {}
            except Exception:
                item[key] = {}
        rows.append(item)
    conn.close()
    return rows

def _merge_credentials(credentials_lists):
    result = []
    seen = set()
    for creds in credentials_lists:
        for cred in creds or []:
            key = (
                (cred.get("label") or "").strip().lower(),
                (cred.get("username") or "").strip().lower(),
                (cred.get("password") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(cred)
    return result

def _merge_sublinks(sublinks_lists):
    result = []
    seen = set()
    for subs in sublinks_lists:
        for sub in subs or []:
            key = (sub.get("url") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(sub)
    return result

def apply_domain_merge(root_domain, main_link_id, link_ids, reason="manual", suggestion_id=None):
    """
    Merges several links of the same root domain into a main link.
    Secondary links are archived (never deleted) and linked via merged_into_id.
    """
    link_ids = [int(i) for i in (link_ids or []) if str(i).isdigit() or isinstance(i, int)]
    main_link_id = int(main_link_id)
    if main_link_id not in link_ids:
        link_ids.append(main_link_id)

    main = get_link_by_id(main_link_id)
    if not main:
        return {"success": False, "error": "El enlace principal no existe."}

    links = []
    for lid in link_ids:
        item = get_link_by_id(lid)
        if item:
            links.append(item)
    if len(links) < 2:
        return {"success": False, "error": "Se necesitan al menos dos enlaces para fusionar."}

    group_setting = get_domain_settings()["group_subdomains"]
    for item in links:
        item_root = item.get("root_domain") or get_root_domain(
            item.get("domain") or item.get("url", ""), group_setting
        )
        if item_root != root_domain:
            return {"success": False, "error": "Todos los enlaces deben pertenecer al mismo dominio."}

    create_auto_backup("pre_domain_merge")

    secondaries = [item for item in links if item["id"] != main_link_id]

    before = {
        "main": {
            "id": main_link_id,
            "credentials": main.get("credentials") or [],
            "sublinks": main.get("sublinks") or [],
            "tags": main.get("tags") or [],
            "notes": main.get("notes") or "",
            "visit_count": main.get("visit_count") or 0,
            "is_favorite": main.get("is_favorite") or 0,
            "is_read": main.get("is_read") or 0,
        },
        "secondaries": [
            {
                "id": item["id"],
                "is_archived": item.get("is_archived") or 0,
                "merged_into_id": item.get("merged_into_id"),
            }
            for item in secondaries
        ],
    }

    merged_credentials = _merge_credentials(
        [main.get("credentials") or []] + [item.get("credentials") or [] for item in secondaries]
    )
    merged_sublinks = _merge_sublinks(
        [main.get("sublinks") or []] + [item.get("sublinks") or [] for item in secondaries]
    )

    merged_tags = []
    for tag in (main.get("tags") or []) + [t for item in secondaries for t in (item.get("tags") or [])]:
        if tag and tag not in merged_tags:
            merged_tags.append(tag)

    notes_parts = []
    for text in [main.get("notes") or ""] + [item.get("notes") or "" for item in secondaries]:
        text = (text or "").strip()
        if text and text not in notes_parts:
            notes_parts.append(text)

    visit_count = sum(int(item.get("visit_count") or 0) for item in links)
    is_favorite = max([int(item.get("is_favorite") or 0) for item in links] or [0])
    is_read = 1 if all(int(item.get("is_read") or 0) for item in links) else int(main.get("is_read") or 0)

    update_link(
        main_link_id,
        credentials=merged_credentials,
        sublinks=merged_sublinks,
        tags=merged_tags,
        notes="\n".join(notes_parts),
        visit_count=visit_count,
        is_favorite=is_favorite,
        is_read=is_read,
    )

    conn = get_connection()
    cursor = conn.cursor()
    for item in secondaries:
        cursor.execute("""
        UPDATE links
        SET is_archived = 1, merged_into_id = ?, updated_at = datetime('now')
        WHERE id = ?
        """, (main_link_id, item["id"]))
    cursor.execute("""
    UPDATE domain_suggestions
    SET status = 'superseded', updated_at = datetime('now')
    WHERE root_domain = ? AND action = 'merge_group' AND status = 'pending'
    """, (root_domain,))
    conn.commit()
    conn.close()

    after = {
        "main": {
            "credentials": merged_credentials,
            "sublinks": merged_sublinks,
            "tags": merged_tags,
            "notes": "\n".join(notes_parts),
            "visit_count": visit_count,
            "is_favorite": is_favorite,
            "is_read": is_read,
        },
        "secondaries": [item["id"] for item in secondaries],
    }

    log_id = _domain_log_action(
        "merge_domain", root_domain, before, after,
        reason or f"Fusión de {len(links)} enlaces de {root_domain}"
    )

    if suggestion_id:
        set_domain_suggestion_status(suggestion_id, "applied")

    return {
        "success": True,
        "main_link_id": main_link_id,
        "merged_count": len(secondaries),
        "log_id": log_id,
    }

def refresh_domain_thumbnails(link_ids, suggestion_id=None):
    """Re-scrapes OpenGraph thumbnails for links that have none."""
    from backend.scraper import extract_metadata

    link_ids = [int(i) for i in (link_ids or []) if str(i).isdigit() or isinstance(i, int)]
    if not link_ids:
        return {"success": False, "error": "No hay enlaces para actualizar."}

    create_auto_backup("pre_domain_thumbnails")
    before = {"links": []}
    updated = 0

    for link_id in link_ids:
        link = get_link_by_id(link_id)
        if not link:
            continue
        before["links"].append({
            "id": link_id,
            "thumbnail_url": link.get("thumbnail_url") or "",
        })
        if link.get("thumbnail_url"):
            continue
        try:
            meta = extract_metadata(link.get("url", ""))
            thumb = meta.get("thumbnail_url") or ""
            if thumb:
                update_link(link_id, thumbnail_url=thumb)
                updated += 1
        except Exception:
            pass

    _domain_log_action(
        "refresh_thumbnail", "", before, {"updated": updated},
        f"Miniaturas recuperadas: {updated}"
    )
    if suggestion_id:
        set_domain_suggestion_status(suggestion_id, "applied")
    return {"success": True, "updated": updated}

def undo_last_domain_action():
    create_auto_backup("pre_domain_undo")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM domain_action_log WHERE undone = 0 ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "No hay acciones recientes para deshacer."}

    log = dict(row)
    conn.close()
    before = {}
    try:
        before = json.loads(log.get("payload_before") or "{}")
    except Exception:
        before = {}

    if log["action"] == "merge_domain":
        main = before.get("main") or {}
        secondaries = before.get("secondaries") or []
        if main.get("id"):
            update_link(
                main["id"],
                credentials=main.get("credentials") or [],
                sublinks=main.get("sublinks") or [],
                tags=main.get("tags") or [],
                notes=main.get("notes") or "",
                visit_count=main.get("visit_count") or 0,
                is_favorite=main.get("is_favorite") or 0,
                is_read=main.get("is_read") or 0,
            )
        conn = get_connection()
        cursor = conn.cursor()
        for item in secondaries:
            cursor.execute("""
            UPDATE links SET is_archived = ?, merged_into_id = ?, updated_at = datetime('now')
            WHERE id = ?
            """, (item.get("is_archived", 0), item.get("merged_into_id"), item.get("id")))
        cursor.execute("UPDATE domain_action_log SET undone = 1 WHERE id = ?", (log["id"],))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Fusión deshecha correctamente."}

    if log["action"] == "refresh_thumbnail":
        for item in before.get("links") or []:
            if item.get("id"):
                update_link(item["id"], thumbnail_url=item.get("thumbnail_url") or "")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE domain_action_log SET undone = 1 WHERE id = ?", (log["id"],))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Miniaturas restauradas."}

    return {"success": False, "error": "Esta acción no se puede deshacer."}

# ============================================================
# ANALYTICS & STATS
# ============================================================
def get_analytics():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT c.name, c.color, COUNT(l.id) as count
    FROM categories c
    LEFT JOIN links l ON c.id = l.category_id AND l.is_archived = 0
    GROUP BY c.id
    HAVING count > 0
    ORDER BY count DESC
    """)
    cat_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT p.name, p.color, COUNT(l.id) as count
    FROM profiles p
    LEFT JOIN links l ON p.id = l.profile_id AND l.is_archived = 0
    GROUP BY p.id
    ORDER BY count DESC
    """)
    prof_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0 AND is_read = 1")
    read_cnt = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0 AND is_read = 0")
    unread_cnt = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0 AND is_favorite = 1")
    fav_cnt = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0")
    active_cnt = cursor.fetchone()[0]

    conn.close()

    return {
        "categories": cat_rows,
        "profiles": prof_rows,
        "status_summary": {
            "read": read_cnt,
            "unread": unread_cnt,
            "favorites": fav_cnt
        },
        "total_active": active_cnt
    }

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 0")
    total_active = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_favorite = 1 AND is_archived = 0")
    total_favorites = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_read = 0 AND is_archived = 0")
    total_unread = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links WHERE is_archived = 1")
    total_archived = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM profiles")
    total_profiles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM categories")
    total_categories = cursor.fetchone()[0]

    conn.close()
    return {
        "total_active": total_active,
        "total_favorites": total_favorites,
        "total_unread": total_unread,
        "total_archived": total_archived,
        "total_profiles": total_profiles,
        "total_categories": total_categories,
        "db_path": DB_PATH
    }
