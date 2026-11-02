"""
Ollama Local AI Service for Pageneitor.
Detects Ollama in root (./ollama.exe) or Windows system, starts service if needed,
lists available models, and generates cyclic dynamic AI advice and alerts.
"""

import os
import sys
import re
import subprocess
import threading
import time
import requests
import json
import random

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OLLAMA_LOCAL_BINARY = os.path.join(BASE_DIR, "ollama.exe")
OLLAMA_LOCAL_MODELS = os.path.join(BASE_DIR, "models")

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"

class OllamaService:
    def __init__(self):
        self.host = DEFAULT_OLLAMA_HOST
        self.selected_model = None
        self.process = None
        self.is_running = False
        self.binary_path = self._find_binary()
        self.models_dir = OLLAMA_LOCAL_MODELS if os.path.exists(OLLAMA_LOCAL_MODELS) else None
        self._check_status()

    def _find_binary(self):
        # 1. Local root folder
        if os.path.exists(OLLAMA_LOCAL_BINARY):
            return OLLAMA_LOCAL_BINARY
        
        # 2. Windows Default AppData Program directory
        appdata_local = os.environ.get("LOCALAPPDATA", "")
        standard_win_path = os.path.join(appdata_local, "Programs", "Ollama", "ollama.exe")
        if os.path.exists(standard_win_path):
            return standard_win_path
            
        # 3. Check PATH
        try:
            result = subprocess.run(["where", "ollama"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                first_line = result.stdout.strip().splitlines()[0]
                if os.path.exists(first_line):
                    return first_line
        except Exception:
            pass

        return None

    def _check_status(self):
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=1.5)
            if r.status_code == 200:
                self.is_running = True
                models_data = r.json().get("models", [])
                if models_data and not self.selected_model:
                    self.selected_model = models_data[0].get("name")
                return True
        except Exception:
            pass
        self.is_running = False
        return False

    def start_ollama(self):
        """Starts Ollama daemon in background."""
        if self._check_status():
            return True, "Ollama ya está en ejecución."

        if not self.binary_path:
            return False, "No se encontró el ejecutable de Ollama en el sistema ni en la raíz."

        env = os.environ.copy()
        if self.models_dir and os.path.exists(self.models_dir):
            env["OLLAMA_MODELS"] = self.models_dir

        try:
            # Launch detached background process
            creationflags = 0x08000000 if sys.platform == "win32" else 0 # CREATE_NO_WINDOW
            self.process = subprocess.Popen(
                [self.binary_path, "serve"],
                env=env,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Give it a moment to boot
            time.sleep(2)
            if self._check_status():
                return True, "Ollama iniciado correctamente."
            return True, "Ollama se está iniciando..."
        except Exception as e:
            return False, f"Error al iniciar Ollama: {str(e)}"

    def get_models(self):
        if not self._check_status():
            return []
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if models and not self.selected_model:
                    self.selected_model = models[0]
                return models
        except Exception:
            pass
        return []

    def set_config(self, host=None, model=None):
        if host:
            self.host = host.rstrip('/')
        if model:
            self.selected_model = model
        self._check_status()
        return self.get_status()

    def get_status(self):
        self._check_status()
        models = self.get_models() if self.is_running else []
        return {
            "binary_found": bool(self.binary_path),
            "binary_path": self.binary_path,
            "has_local_models_dir": bool(self.models_dir),
            "is_running": self.is_running,
            "host": self.host,
            "selected_model": self.selected_model or (models[0] if models else None),
            "available_models": models
        }

    def chat_reply(self, messages, context_text="", max_chars=320):
        """
        Short, grounded assistant reply. Returns {'text', 'source'} or None.
        Uses Ollama /api/chat and falls back to /api/generate for older builds.
        """
        if not self._check_status() and self.binary_path:
            # Lazily start the local Ollama service on first assistant use.
            self.start_ollama()

        if not self._check_status() or not self.selected_model:
            return None

        system_prompt = (
            "Eres el asistente local de Pageneitor. Ayudas a buscar y abrir enlaces "
            "guardados por el usuario. Responde SIEMPRE en español, de forma directa, "
            "amable y muy breve: máximo 2 frases (35 palabras). Usa únicamente los "
            "datos del CONTEXTO. Nunca inventes enlaces, títulos, temas, perfiles ni "
            "cifras. Si hay resultados, menciona cuántos y sugiere abrirlos. Nunca digas "
            "que ya abriste un enlace: el usuario debe pulsarlo. Si no hay resultados, "
            "dilo y propone otro término."
        )

        api_messages = [{"role": "system", "content": system_prompt}]
        if context_text:
            api_messages.append({
                "role": "system",
                "content": "CONTEXTO ACTUAL:\n" + context_text[:4000]
            })
        for m in messages[-8:]:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                api_messages.append({"role": role, "content": content[:900]})

        # Preferred modern endpoint
        try:
            res = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.selected_model,
                    "messages": api_messages,
                    "stream": False,
                    "options": {"temperature": 0.25, "num_predict": 110}
                },
                timeout=25
            )
            if res.status_code == 200:
                payload = res.json()
                text = (payload.get("message") or {}).get("content", "") or payload.get("response", "")
                text = self._clean_chat_text(text, max_chars)
                if text:
                    return {"text": text, "source": f"Ollama ({self.selected_model})"}
        except Exception as e:
            print(f"[Ollama] Chat fallback: {e}")

        # Older Ollama versions / generate endpoint
        try:
            prompt = system_prompt + "\n\n"
            if context_text:
                prompt += "CONTEXTO:\n" + context_text[:4000] + "\n\n"
            for m in messages[-6:]:
                if m.get("role") in ("user", "assistant"):
                    prompt += f"{m['role']}: {m.get('content', '')[:700]}\n"
            prompt += "assistant:"
            res = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.25, "num_predict": 110}
                },
                timeout=25
            )
            if res.status_code == 200:
                text = self._clean_chat_text(res.json().get("response", ""), max_chars)
                if text:
                    return {"text": text, "source": f"Ollama ({self.selected_model})"}
        except Exception as e:
            print(f"[Ollama] Chat generate fallback: {e}")

        return None

    def domain_suggestions(self, context_text):
        """
        Asks Ollama for domain grouping suggestions in strict JSON.
        Returns a list, an empty list, or None if the LLM is unavailable.
        """
        if not self._check_status() and self.binary_path:
            self.start_ollama()
        if not self._check_status() or not self.selected_model:
            return None

        prompt = (
            "Eres el analizador de dominios de Pageneitor. Recibes grupos de enlaces "
            "del mismo dominio. Debes proponer SOLO acciones seguras y útiles.\n\n"
            "Devuelve EXCLUSIVAMENTE un array JSON válido, sin markdown ni texto extra.\n"
            "Esquema permitido:\n"
            '[{"action":"merge_group","root_domain":"github.com","main_link_id":12,'
            '"link_ids":[12,15],"confidence":0.82,"reason":"frase breve"},\n'
            ' {"action":"refresh_thumbnail","root_domain":"figma.com",'
            '"link_ids":[3],"confidence":0.75,"reason":"frase breve"}]\n\n'
            "Reglas:\n"
            "- merge_group solo si los enlaces son variantes o recursos muy relacionados "
            "del mismo dominio y fusionarlos no haría perder información.\n"
            "- El main_link_id debe estar dentro de link_ids y ser el enlace más completo "
            "(más visitas, favorito, credenciales o sub-enlaces).\n"
            "- refresh_thumbnail solo para enlaces que no tienen miniatura.\n"
            "- No propongas fusionar recursos claramente distintos (ej. proyectos distintos "
            "de github.com/usuario/repo-a y repo-b).\n"
            "- Máximo 5 sugerencias. confidence entre 0 y 1. reason máximo 18 palabras.\n"
            "- Si no hay nada útil, devuelve [].\n\n"
            "GRUPOS:\n" + (context_text or "")[:5000]
        )

        try:
            res = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.15, "num_predict": 420}
                },
                timeout=45
            )
            if res.status_code == 200:
                raw = res.json().get("response", "")
                parsed = self._parse_json_array(raw)
                if parsed is not None:
                    return parsed
        except Exception as e:
            print(f"[Ollama] Domain suggestions fallback: {e}")
        return None

    def classify_links(self, context_text):
        """Classifies a batch of links into existing or proposed taxonomy."""
        if not self._check_status() and self.binary_path:
            self.start_ollama()
        if not self._check_status() or not self.selected_model:
            return None

        prompt = (
            "Eres el clasificador de enlaces de Pageneitor. Recibes categorías y perfiles "
            "existentes y una lista de enlaces nuevos. Devuelve EXCLUSIVAMENTE un array "
            "JSON, sin markdown, con un objeto por enlace (mismo índice):\n"
            '{"index":0,"category_id":2,"profile_id":1,"tags":["tag1","tag2"],'
            '"confidence":0.82,"reason":"frase breve",'
            '"new_category":{"name":"Nombre","color":"#8b5cf6","icon":"fa-folder",'
            '"reason":"por qué hace falta"},"new_profile":{"name":"Nombre",'
            '"color":"#6366f1","icon":"fa-user","reason":"por qué hace falta"}}\n\n'
            "Reglas:\n"
            "- Usa category_id/profile_id existentes siempre que encajen.\n"
            "- new_category/new_profile solo si NINGUNA opción existente encaja; "
            "incluye name, color e icon de Font Awesome. Si no hace falta, omite esas claves.\n"
            "- tags: 2 a 5 etiquetas cortas en español, sin #.\n"
            "- confidence entre 0 y 1. reason máximo 15 palabras.\n"
            "- No inventes IDs que no aparezcan en las listas.\n\n"
            "DATOS:\n" + (context_text or "")[:7000]
        )
        try:
            res = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.15, "num_predict": 1400}
                },
                timeout=60
            )
            if res.status_code == 200:
                raw = res.json().get("response", "")
                text = raw.replace("```json", "").replace("```", "").strip()
                start, end = text.find("["), text.rfind("]")
                if start >= 0 and end > start:
                    data = json.loads(text[start:end + 1])
                    return data if isinstance(data, list) else None
        except Exception as e:
            print(f"[Ollama] Link classification fallback: {e}")
        return None

    def analytics_insights(self, context_text):
        """Returns a short list of data insights generated locally."""
        if not self._check_status() and self.binary_path:
            self.start_ollama()
        if not self._check_status() or not self.selected_model:
            return None

        prompt = (
            "Eres el analista de datos local de Pageneitor. Recibes métricas agregadas "
            "del banco de enlaces del usuario. Devuelve EXCLUSIVAMENTE un array JSON de "
            "4 a 6 strings en español, sin markdown. Cada insight debe ser breve "
            "(máximo 22 palabras), concreto y basado SOLO en las métricas. Incluye una "
            "recomendación práctica cuando sea útil. No inventes cifras.\n\n"
            "MÉTRICAS:\n" + (context_text or "")[:5000]
        )
        try:
            res = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 320}
                },
                timeout=45
            )
            if res.status_code == 200:
                raw = res.json().get("response", "")
                text = raw.replace("```json", "").replace("```", "").strip()
                start, end = text.find("["), text.rfind("]")
                if start >= 0 and end > start:
                    data = json.loads(text[start:end + 1])
                    if isinstance(data, list):
                        return [str(x)[:220] for x in data if str(x).strip()][:6]
        except Exception as e:
            print(f"[Ollama] Analytics insights fallback: {e}")
        return None

    def wordcloud_keywords(self, content_text, sets=3, words_per_set=24):
        """Returns several LLM-generated keyword/weight sets for the background."""
        if not self._check_status() and self.binary_path:
            self.start_ollama()
        if not self._check_status() or not self.selected_model:
            return None

        prompt = (
            "Analiza el siguiente contenido de enlaces de un usuario. Extrae palabras "
            "clave y conceptos recurrentes en español (también nombres propios y "
            "tecnologías). No uses palabras vacías. Devuelve EXCLUSIVAMENTE un array "
            f"JSON de {sets} conjuntos; cada conjunto debe tener hasta {words_per_set} "
            'objetos {"text":"palabra","weight":1-100}. Sin markdown ni texto extra. '
            "Los conjuntos deben variar entre sí.\n\nCONTENIDO:\n" + (content_text or "")[:6000]
        )
        try:
            res = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.selected_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.35, "num_predict": 1200}
                },
                timeout=60
            )
            if res.status_code == 200:
                raw = res.json().get("response", "")
                text = raw.replace("```json", "").replace("```", "").strip()
                start, end = text.find("["), text.rfind("]")
                if start >= 0 and end > start:
                    data = json.loads(text[start:end + 1])
                    if isinstance(data, list):
                        clean_sets = []
                        for group in data[:sets]:
                            if not isinstance(group, list):
                                continue
                            clean = []
                            for item in group[:words_per_set]:
                                if not isinstance(item, dict):
                                    continue
                                word = str(item.get("text", "")).strip()
                                if not word:
                                    continue
                                try:
                                    weight = max(1, min(100, int(item.get("weight", 50))))
                                except Exception:
                                    weight = 50
                                clean.append({"text": word[:40], "weight": weight})
                            if clean:
                                clean_sets.append(clean)
                        if clean_sets:
                            return clean_sets
        except Exception as e:
            print(f"[Ollama] Wordcloud fallback: {e}")
        return None

    @staticmethod
    def _parse_json_array(raw):
        text = (raw or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            # Some models return a single object.
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = "[" + text[start:end + 1] + "]"
            else:
                return None
        else:
            text = text[start:end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else None
        except Exception:
            return None

    @staticmethod
    def _clean_chat_text(text, max_chars=240):
        text = (text or "").strip()
        text = text.replace("**", "").replace("###", "").replace("`", "")
        # Models sometimes append bullet lists; the UI already renders the
        # actual result cards, so keep only the conversational sentence.
        text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*\n+\s*", " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" :")
        if not text:
            return ""
        if len(text) > max_chars:
            cut = text[:max_chars]
            last_dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            text = cut[:last_dot + 1] if last_dot > 80 else cut.rstrip() + "…"
        return text

    def generate_cyclic_tip(self, context=None):
        """
        Generates a non-static, dynamic, cyclic AI tip/advice.
        Uses local Ollama if online; otherwise uses a rich procedural generator
        so messages are NEVER static.
        """
        context = context or {}
        level = context.get("level", 1)
        level_title = context.get("level_title", "Novato")
        ram_saved = context.get("ram_saved", "~1.2 GB")
        links_count = context.get("links_count", 0)

        # 1. Try local Ollama LLM if available
        if self._check_status() and self.selected_model:
            try:
                prompts = [
                    f"Eres Pageneitor AI, un asistente de productividad y limpieza de pestañas para navegador. El usuario está en Nivel {level} ('{level_title}') y ha salvado {ram_saved} de RAM. Dale un consejo muy breve, entusiasta e ingenioso de 2 oraciones en español para no acumular pestañas hoy.",
                    f"Eres el consejero de Pageneitor. El usuario tiene {links_count} enlaces catalogados y Nivel {level}. Escribe una frase corta y motivacional gamer en español sobre el arte de tener cero pestañas abiertas y mantener la mente clara.",
                    f"Dame una recomendación táctica y concisa (máximo 30 palabras) en español para organizar enlaces por temas en vez de dejarlos en pestañas muertas del navegador."
                ]
                selected_prompt = random.choice(prompts)
                
                payload = {
                    "model": self.selected_model,
                    "prompt": selected_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.75,
                        "num_predict": 75
                    }
                }
                res = requests.post(f"{self.host}/api/generate", json=payload, timeout=8)
                if res.status_code == 200:
                    text = res.json().get("response", "").strip()
                    if text:
                        return {
                            "source": f"Ollama ({self.selected_model})",
                            "tip": text,
                            "type": "ai"
                        }
            except Exception as e:
                print(f"[Ollama] Generation fallback: {e}")

        # 2. Dynamic Procedural Generator (NEVER static, uses dynamic metrics & randomizers)
        themes = ["RAM", "Enfoque", "Organización", "Rango", "Hábito"]
        t = random.choice(themes)

        procedural_tips = [
            f"🧠 Nivel {level} detectado: Tu equipo agradece los {ram_saved} de RAM liberados. Mantén solo 1 pestaña de trabajo activa.",
            f"⚡ Sabiduría Antitab: Una pestaña guardada en Pageneitor es una victoria para tu procesador. ¡Sigue podando enlaces antiguos!",
            f"🛡️ Desafío del día: Si no has abierto un enlace en más de 2 semanas, elimínalo para ganar +25 XP de Poda Saludable.",
            f"🎮 Consejo de Rango: Para avanzar de '{level_title}' a la siguiente liga, prueba importar lotes y clasificar por perfiles de usuario.",
            f"🚀 Tu banco visual cuenta con {links_count} enlaces catalogados. ¡Eso equivale a no tener {links_count} pestañas ralentizando Chrome o Edge!",
            f"💎 Modo Perfeccionista: Añade notas y etiquetas a tus enlaces pendientes para ganar trofeos dorados.",
            f"🧹 Limpieza Activa: Recuerda que los puntos de XP decaen con la inactividad prolongada. ¡Usa Pageneitor a diario!"
        ]

        return {
            "source": "Pageneitor Smart Engine",
            "tip": random.choice(procedural_tips),
            "type": "procedural"
        }

ollama_service = OllamaService()
