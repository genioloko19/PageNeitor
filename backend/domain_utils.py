"""
Domain normalization helpers for Pageneitor.

The assistant groups links by their registrable ("root") domain so that
docs.github.com, gist.github.com and www.github.com all belong to github.com.
The public-suffix list is intentionally small and offline: enough for normal
day-to-day browsing without adding another runtime dependency.
"""

import ipaddress
import re
from urllib.parse import urlparse


# Multi-label public suffixes where the registrable domain needs 3 labels.
MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "me.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "id.au",
    "co.nz", "net.nz", "org.nz", "govt.nz",
    "com.br", "net.br", "org.br", "com.ar", "net.ar", "org.ar",
    "com.mx", "net.mx", "org.mx", "com.co", "net.co", "org.co",
    "com.pe", "net.pe", "org.pe", "com.cl", "com.ve", "com.ec",
    "com.uy", "com.py", "com.bo", "com.do", "com.gt", "com.sv",
    "com.hn", "com.ni", "com.pa", "com.cr",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "co.kr", "or.kr", "ne.kr", "re.kr",
    "com.cn", "net.cn", "org.cn", "gov.cn",
    "com.hk", "com.tw", "com.sg", "com.my", "com.ph", "com.vn",
    "co.id", "co.in", "net.in", "org.in", "gen.in", "firm.in",
    "co.za", "org.za", "net.za", "com.tr", "com.ua", "com.ru",
    "com.eg", "com.sa", "com.pk", "com.bd", "com.np", "com.kw",
    "com.qa", "com.om", "com.bh", "com.jo", "com.lb",
    # Shared application hosts: treat each user site as its own registrable host.
    "github.io", "gitlab.io", "herokuapp.com", "appspot.com",
    "vercel.app", "netlify.app", "pages.dev", "workers.dev",
    "blogspot.com", "wordpress.com", "tumblr.com", "notion.site",
}

_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def extract_host(url_or_host):
    """Returns a clean lowercase host from a URL or bare hostname."""
    value = (url_or_host or "").strip()
    if not value:
        return ""

    if "://" not in value:
        value = "https://" + value

    try:
        parsed = urlparse(value)
        host = parsed.hostname or parsed.netloc or ""
    except Exception:
        host = value

    host = host.split("@")[-1].split(":")[0].strip().lower().rstrip(".")
    if not host:
        return ""

    # Internationalized domains -> ASCII (punycode) for stable grouping.
    try:
        host = host.encode("idna").decode("ascii")
    except Exception:
        pass
    return host


def get_root_domain(url_or_host, group_subdomains=True):
    """
    Returns the main domain used for grouping.
    With group_subdomains=False only 'www.' is removed and the rest of the
    subdomain is preserved.
    """
    host = extract_host(url_or_host)
    if not host:
        return ""

    if host == "localhost" or _IP_RE.match(host):
        return host

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass

    # 'www' is never a meaningful group by itself.
    if host.startswith("www."):
        host = host[4:]

    if not group_subdomains:
        return host

    parts = host.split(".")
    if len(parts) <= 2:
        return host

    last_two = ".".join(parts[-2:])
    if last_two in MULTI_LABEL_SUFFIXES:
        # example.co.uk -> example.co.uk
        return ".".join(parts[-3:])

    # docs.github.com -> github.com
    return last_two


def domain_label(root_domain):
    """Human-friendly label for a group header."""
    if not root_domain:
        return "Sin dominio"
    return root_domain
