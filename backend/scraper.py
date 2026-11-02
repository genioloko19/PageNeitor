"""
Scraper and metadata extractor for Pageneitor.
Extracts title, description, OpenGraph image, favicon, and auto-detects topics.
Includes resilient fallback when offline or pages block crawlers.
"""

import re
import urllib.parse
from html.parser import HTMLParser
import requests

class MetaExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""
        self.meta = {}
        self.icons = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        if tag_lower == 'title':
            self.in_title = True

        elif tag_lower == 'meta':
            # Check property or name
            prop = attrs_dict.get('property', '').lower()
            name = attrs_dict.get('name', '').lower()
            content = attrs_dict.get('content', '')

            key = prop or name
            if key and content:
                self.meta[key] = content

        elif tag_lower == 'link':
            rel = attrs_dict.get('rel', '').lower()
            href = attrs_dict.get('href', '')
            if href and any(x in rel for x in ['icon', 'apple-touch-icon', 'shortcut icon', 'image_src']):
                self.icons.append({'rel': rel, 'href': href})

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def clean_text(text: str) -> str:
    if not text:
        return ""
    # Remove excessive whitespace, HTML entities, and truncate
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300]

def detect_category_and_tags(domain: str, title: str, description: str):
    """Smart heuristic to categorize link and propose tags."""
    content = f"{domain} {title} {description}".lower()
    
    # Rules for categories
    if any(k in content for k in ['github', 'gitlab', 'stackoverflow', 'python', 'javascript', 'api', 'react', 'code', 'npm', 'rust', 'docker', 'dev.to', 'git', 'terminal', 'backend', 'frontend']):
        return 1, ['código', 'desarrollo', 'tech'] # Desarrollo Web & Código
    
    if any(k in content for k in ['figma', 'dribbble', 'behance', 'ui', 'ux', 'color', 'palette', 'icon', 'font', 'typography', 'css', 'design', 'canvas', 'svg']):
        return 2, ['diseño', 'ui-ux', 'creatividad'] # Diseño & UI/UX
        
    if any(k in content for k in ['ai', 'gpt', 'openai', 'gemini', 'claude', 'anthropic', 'prompt', 'llm', 'deep learning', 'machine learning', 'huggingface', 'neural', 'midjourney', 'mistral']):
        return 3, ['ia', 'machine-learning', 'automatización'] # Inteligencia Artificial
        
    if any(k in content for k in ['doc', 'documentation', 'manual', 'guide', 'tutorial', 'cheatsheet', 'reference', 'learn', 'wiki', 'wikipedia', 'course']):
        return 4, ['documentación', 'guía', 'aprendizaje'] # Documentación & Guías
        
    if any(k in content for k in ['finance', 'bank', 'crypto', 'bitcoin', 'inversión', 'money', 'stock', 'trading', 'presupuesto', 'business', 'stripe', 'paypal']):
        return 5, ['finanzas', 'negocios', 'economía'] # Finanzas & Negocios
        
    if any(k in content for k in ['news', 'noticia', 'article', 'blog', 'substack', 'medium', 'read', 'libro', 'post', 'ensayo']):
        return 6, ['lectura', 'artículos', 'para-leer'] # Lectura & Artículos
        
    if any(k in content for k in ['tool', 'utility', 'converter', 'calculator', 'online tool', 'compress', 'generator', 'app', 'saas']):
        return 7, ['herramientas', 'utilidad'] # Herramientas & Utilidades
        
    if any(k in content for k in ['youtube', 'vimeo', 'netflix', 'twitch', 'music', 'spotify', 'movie', 'game', 'podcast', 'video', 'tiktok']):
        return 8, ['multimedia', 'video', 'ocio'] # Entretenimiento & Videos

    return 7, ['web']

def extract_metadata(raw_url: str) -> dict:
    url = normalize_url(raw_url)
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc or parsed.path.split('/')[0]
    
    # Strip port if any
    clean_domain = domain.split(':')[0]
    
    # Default fallbacks
    data = {
        "url": url,
        "domain": clean_domain,
        "title": clean_domain.capitalize(),
        "description": f"Enlace guardado de {clean_domain}",
        "thumbnail_url": "",
        "favicon_url": f"https://www.google.com/s2/favicons?domain={clean_domain}&sz=64",
        "category_id": 7,
        "suggested_tags": ["guardado"]
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
    }

    try:
        response = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
        if response.status_code == 200:
            html = response.text
            parser = MetaExtractor()
            parser.feed(html)

            # 1. Title
            title = (
                parser.meta.get('og:title') or
                parser.meta.get('twitter:title') or
                parser.title or
                clean_domain
            )
            data["title"] = clean_text(title)

            # 2. Description
            description = (
                parser.meta.get('og:description') or
                parser.meta.get('twitter:description') or
                parser.meta.get('description') or
                ""
            )
            data["description"] = clean_text(description)

            # 3. OpenGraph / Twitter Image (Thumbnail)
            image_url = (
                parser.meta.get('og:image') or
                parser.meta.get('og:image:secure_url') or
                parser.meta.get('twitter:image') or
                parser.meta.get('twitter:image:src')
            )
            if image_url:
                data["thumbnail_url"] = urllib.parse.urljoin(url, image_url)
            else:
                for icon in parser.icons:
                    if 'image_src' in icon['rel']:
                        data["thumbnail_url"] = urllib.parse.urljoin(url, icon['href'])
                        break

            # 4. Favicon
            favicon = None
            for icon in parser.icons:
                if any(x in icon['rel'] for x in ['icon', 'shortcut icon', 'apple-touch-icon']):
                    favicon = urllib.parse.urljoin(url, icon['href'])
                    break
            if favicon:
                data["favicon_url"] = favicon

    except Exception as e:
        # Resilient: If network fails or timeout occurs, fallback to sensible domain info
        print(f"[Scraper] Warning extracting {url}: {e}")

    # Auto detect category and suggested tags
    cat_id, tags = detect_category_and_tags(clean_domain, data["title"], data["description"])
    data["category_id"] = cat_id
    data["suggested_tags"] = tags

    return data
