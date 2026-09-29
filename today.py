#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Daily Profile & SVG Updater (today.py)
 Emanuel Lopez F (ema28pro)
-----------------------------------------------------------------------------
 - Genera el SVG CodeMe.svg directamente desde template.txt (sin regex frágiles).
 - Calcula dinámicamente Uptime y Age con años, meses y días (estilo pyoneer).
 - Muestra métricas de GitHub en vivo:
     * Contribs, Repos, Stars
     * Líneas de código agregadas (++addlines) y eliminadas (--deletedlines)
 - Aplica la paleta de colores oficial:
     * Gris oscuro (#4a4a4a): Línea 1 (nombre y usuario)
     * Naranja     (#ffa657): Claves antes de los dos puntos (:)
     * Azul        (#a5d6ff): Textos de valores, tecnologías y números
     * Verde       (#3fb950): Líneas de código agregadas (++)
     * Rojo        (#f85149): Líneas de código eliminadas (--)
     * Gris/Blanco (#c9d1d9): Cráneo ASCII, separadores, dos puntos y comentarios (#)
 - Realiza git add, commit y push automático a GitHub.
=============================================================================
"""

import sys
import os
import re
import json
import html
import datetime
import subprocess
from dateutil import relativedelta
import requests

# Configurar salida UTF-8 en terminales de Windows
if sys.platform.startswith("win"):
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# =============================================================================
# CARGA DE VARIABLES DE ENTORNO (.env)
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_dotenv(filepath: str = None):
    """Carga variables desde el archivo .env si existe."""
    if filepath is None:
        filepath = os.path.join(BASE_DIR, ".env")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val

load_dotenv()

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
USER_NAME = os.environ.get("GITHUB_USER", "ema28pro")
BIRTHDAY = datetime.date(2005, 11, 28)       # 28 de Noviembre de 2005
UPTIME_START = datetime.date(2022, 5, 1)      # Mayo de 2022

TEMPLATE_PATH = os.path.join(BASE_DIR, "template.txt")
SVG_PATH = os.path.join(BASE_DIR, "img", "CodeMe.svg")
LOC_FILE = os.path.join(BASE_DIR, "loc.json")

ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")

# Colores oficiales
C_ORANGE = "#ffa657"   # Naranja (Keys / Identificadores)
C_BASE = "#c9d1d9"     # Blanco / Gris base (ASCII skull, separadores, :, comentarios #)
C_BLUE = "#a5d6ff"     # Azul (Valores, tecnologías, números)
C_DARK = "#4a4a4a"     # Gris oscuro (Línea 1 del perfil)
C_GREEN = "#3fb950"    # Verde ++ (Líneas agregadas)
C_RED = "#f85149"      # Rojo -- (Líneas eliminadas)


# =============================================================================
# CÁLCULOS TEMPORALES
# =============================================================================
def format_unit(val: int, unit: str) -> str:
    """Retorna número y unidad formateada con plural según corresponda."""
    return f"{val} {unit}{'s' if val != 1 else ''}"


def calculate_uptime(today: datetime.date) -> str:
    """Calcula Uptime en años, meses y días desde mayo 2022."""
    diff = relativedelta.relativedelta(today, UPTIME_START)
    parts = []
    if diff.years > 0:
        parts.append(format_unit(diff.years, "year"))
    if diff.months > 0:
        parts.append(format_unit(diff.months, "month"))
    if diff.days > 0 or not parts:
        parts.append(format_unit(diff.days, "day"))
    return ", ".join(parts)


def calculate_age(today: datetime.date) -> str:
    """
    Calcula la edad en años completos desde 28/nov/2005.
    Si hoy es el cumpleaños, agrega pastel 🎂.
    """
    diff = relativedelta.relativedelta(today, BIRTHDAY)
    years = diff.years
    suffix = " 🎂" if (diff.months == 0 and diff.days == 0) else ""
    return f"{years} years{suffix}"


# =============================================================================
# RECOLECCIÓN DE MÉTRICAS DE GITHUB
# =============================================================================
def get_github_stats(username: str, token: str = None) -> dict:
    """
    Obtiene las estadísticas de GitHub del usuario:
    - contribs: total de contribuciones (último año o histórico)
    - repos: total de repositorios públicos
    - stars: total de estrellas recibidas en repositorios
    """
    stats = {
        "contribs": 0,
        "repos": 0,
        "stars": 0,
    }

    headers = {"User-Agent": f"today-script-{username}"}
    if token:
        headers["Authorization"] = f"token {token}"

    # 1. Repos públicos
    try:
        user_url = f"https://api.github.com/users/{username}"
        res = requests.get(user_url, headers=headers, timeout=10)
        if res.status_code == 200:
            user_data = res.json()
            stats["repos"] = user_data.get("public_repos", 0)
    except Exception as e:
        print(f"  [!] Advertencia al obtener datos de usuario: {e}")

    # 2. Estrellas totales
    try:
        repos_url = f"https://api.github.com/users/{username}/repos?per_page=100"
        res = requests.get(repos_url, headers=headers, timeout=10)
        if res.status_code == 200:
            repos_data = res.json()
            stats["stars"] = sum(repo.get("stargazers_count", 0) for repo in repos_data)
    except Exception as e:
        print(f"  [!] Advertencia al obtener estrellas: {e}")

    # 3. Contribuciones del último año (GraphQL o scraping público)
    if token:
        try:
            graphql_query = """
            query($login: String!) {
                user(login: $login) {
                    contributionsCollection {
                        contributionCalendar {
                            totalContributions
                        }
                    }
                }
            }"""
            g_res = requests.post(
                "https://api.github.com/graphql",
                json={"query": graphql_query, "variables": {"login": username}},
                headers={"Authorization": f"token {token}"},
                timeout=10,
            )
            if g_res.status_code == 200:
                calendar = g_res.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]
                stats["contribs"] = calendar.get("totalContributions", 0)
        except Exception as e:
            print(f"  [!] GraphQL falló, intentando fallback público: {e}")

    if not stats["contribs"]:
        try:
            contrib_url = f"https://github.com/users/{username}/contributions"
            res = requests.get(contrib_url, headers=headers, timeout=10)
            if res.status_code == 200:
                match = re.search(r"([0-9,]+)\s+contributions\s+in\s+the\s+last\s+year", res.text)
                if match:
                    stats["contribs"] = int(match.group(1).replace(",", ""))
        except Exception as e:
            print(f"  [!] Advertencia al obtener contribuciones: {e}")

    return stats


def get_saved_loc() -> dict:
    """
    Lee las líneas agregadas y eliminadas desde loc.json de forma instantánea.
    Para recalcular el histórico completo en cualquier momento, ejecuta: python update_loc.py
    """
    if os.path.exists(LOC_FILE):
        try:
            with open(LOC_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [!] Advertencia al leer {LOC_FILE}: {e}")
    return {"additions": 245769, "deletions": 41122, "commits": 726}


# =============================================================================
# TOKENIZADOR Y GENERADOR DE SVG
# =============================================================================
def parse_val_text(val_text: str, tokens: list):
    """
    Parsea texto de valor. Si contiene ( ... ), dentro de los paréntesis
    cualquier ++... se colorea de Verde (#3fb950) y --... de Rojo (#f85149).
    Fuera de los paréntesis, todo permanece en Azul (#a5d6ff) (así C++ nunca se afecta).
    """
    for part in re.split(r'(\([^)]*\))', val_text):
        if part.startswith("(") and part.endswith(")"):
            tokens.append(("(", C_BASE))
            for word in re.split(r'(\s+)', part[1:-1]):
                if word.startswith("++"):
                    tokens.append((word, C_GREEN))
                elif word.startswith("--"):
                    tokens.append((word, C_RED))
                elif word:
                    tokens.append((word, C_BLUE))
            tokens.append((")", C_BASE))
        elif part:
            tokens.append((part, C_BLUE))


def tokenize_line(line_str: str, line_idx: int) -> list:
    """
    Separa cada línea en arte ASCII (col 0-54) y texto derecho (col 55+).
    Aplica las reglas exactas:
    - Arte ASCII: Gris base (#c9d1d9)
    - Primera línea separada: Gris oscuro (#4a4a4a)
    - Separadores (——————): Gris base (#c9d1d9)
    - Texto antes de ':' (sin espacios): Naranja (#ffa657)
    - Los ':' : Gris base (#c9d1d9)
    - Texto de valores: Azul (#a5d6ff)
    - Dentro de ( ... ): ++ en Verde (#3fb950) y -- en Rojo (#f85149)
    - Texto a partir de '#' (inclusive): Gris base (#c9d1d9)
    """
    tokens = []
    if len(line_str) <= 55:
        tokens.append((line_str, C_BASE))
        return tokens

    skull_part = line_str[:55]
    info_part = line_str[55:]

    tokens.append((skull_part, C_BASE))

    # Regla 1: Primera línea separada del ASCII art -> Gris oscuro (#4a4a4a)
    if line_idx == 0:
        tokens.append((info_part, C_DARK))
        return tokens

    # Separadores (ej: ——————) -> Gris (#c9d1d9)
    if info_part.strip().startswith("—"):
        tokens.append((info_part, C_BASE))
        return tokens

    # Separar parte con '#' (comentarios)
    if "#" in info_part:
        hash_idx = info_part.index("#")
        pre_hash = info_part[:hash_idx]
        hash_text = info_part[hash_idx:]
    else:
        pre_hash = info_part
        hash_text = ""

    # Palabras clave sin espacios seguidas de ':' (ej: Description:, Contribs:, Repos:, Stars:, GitHub.Stats:)
    pattern = re.compile(r'([A-Za-z0-9_.-]+)(:)')

    pos = 0
    for m in pattern.finditer(pre_hash):
        key_start, colon_end = m.span()
        key_name = m.group(1)
        colon = m.group(2)

        if key_start > pos:
            val_text = pre_hash[pos:key_start]
            parse_val_text(val_text, tokens)

        tokens.append((key_name, C_ORANGE))
        tokens.append((colon, C_BASE))
        pos = colon_end

    # Texto restante después del último ':'
    if pos < len(pre_hash):
        val_text = pre_hash[pos:]
        parse_val_text(val_text, tokens)

    # Regla: texto después de # y con la # gris
    if hash_text:
        tokens.append((hash_text, C_BASE))

    return tokens


def generate_svg_from_template(template_path: str, svg_path: str, variables: dict) -> bool:
    """
    Lee template.txt, interpola las variables y genera un archivo SVG vectorial ultra ligero (~5 KB).
    Retorna True si el archivo cambió o fue generado exitosamente.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"No se encontró el template en: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    rendered_text = template.format(**variables)
    lines = rendered_text.splitlines()

    char_width = 7.7    # Ancho de cada caracter en pixeles (Consolas 14px ≈ 7.7-8px, usar 8 evita que se corte)
    line_height = 16  # Altura de cada línea en pixeles
    font_size = 14    # Tamaño de la fuente en pixeles
    padding_x = 20    # Margen izquierdo y derecho
    padding_y = 20    # Margen superior e inferior

    max_len = max(len(line) for line in lines)
    svg_width = int(max_len * char_width + padding_x * 2)
    svg_height = int(len(lines) * line_height + padding_y * 2)

    svg_lines = []
    for idx, line in enumerate(lines):
        y_pos = padding_y + (idx + 1) * line_height - 5
        tokens = tokenize_line(line, idx)
        line_tspans = "".join(
            f'<tspan fill="{col}">{html.escape(txt)}</tspan>'
            for txt, col in tokens
        )
        svg_lines.append(f'    <text xml:space="preserve" x="{padding_x}" y="{y_pos}">{line_tspans}</text>')

    content_svg = "\n".join(svg_lines)

    new_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}">
  <defs>
    <style>
      .terminal {{
        font-family: Consolas, "Courier New", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, "Liberation Mono", monospace;
        font-size: {font_size}px;
      }}
    </style>
  </defs>

  <!-- Background Card -->
  <rect width="100%" height="100%" rx="5" fill="#151718"/>

  <!-- Terminal Text -->
  <g class="terminal">
{content_svg}
  </g>
</svg>
"""
    old_svg = ""
    if os.path.exists(svg_path):
        with open(svg_path, "r", encoding="utf-8") as f:
            old_svg = f.read()

    if new_svg != old_svg:
        os.makedirs(os.path.dirname(svg_path), exist_ok=True)
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(new_svg)
        return True

    return False


# =============================================================================
# AUTOMATIZACIÓN DE GIT
# =============================================================================
def run_git(args: list) -> subprocess.CompletedProcess:
    """Ejecuta un comando git en el directorio del proyecto."""
    return subprocess.run(
        ["git"] + args,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def perform_git_workflow(uptime_str: str, age_str: str, stats: dict, push: bool = True) -> bool:
    """
    Ejecuta git add, commit y push con mensaje formateado.
    """
    # 1. Comprobar cambios
    status_proc = run_git(["status", "--porcelain"])
    if not status_proc.stdout.strip():
        print("  [*] No hay cambios pendientes en el repositorio.")
        return False

    # 2. git add
    print("  [+] Ejecutando: git add img/CodeMe.svg template.txt today.py daily.ps1 loc.json update_loc.py .gitignore")
    run_git(["add", "img/CodeMe.svg", "template.txt", "today.py", "daily.ps1", "loc.json", "update_loc.py", ".gitignore"])

    # 3. git commit
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    commit_msg = (
        f"chore(stats): daily update {today_str} "
        f"[Uptime: {uptime_str}, Age: {age_str}, {stats.get('contribs', 0)} contribs]"
    )
    print(f"  [+] Creando commit: \"{commit_msg}\"")
    commit_proc = run_git(["commit", "-m", commit_msg])

    if commit_proc.returncode != 0:
        print(f"  [!] Error al crear commit: {commit_proc.stderr}")
        return False

    # 4. git push
    if push:
        print("  [+] Sincronizando con remoto (git pull --rebase origin main)...")
        run_git(["pull", "--rebase", "origin", "main"])
        print("  [+] Enviando cambios a GitHub (git push origin main)...")
        push_proc = run_git(["push", "origin", "main"])
        if push_proc.returncode == 0:
            print("  [✓] ¡Push completado con éxito!")
            return True
        else:
            print(f"  [!] Error en git push:\n{push_proc.stderr}")
            return False

    return True


# =============================================================================
# PUNTO DE ENTRADA PRINCIPAL (CLI)
# =============================================================================
def main():
    print("\n=======================================================")
    print(" 🚀 Daily Profile Updater - Emanuel Lopez (@ema28pro)")
    print("=======================================================\n")

    today = datetime.date.today()
    print(f"📅 Fecha actual: {today.strftime('%d/%m/%Y')}")

    dry_run = "--dry-run" in sys.argv
    no_push = "--no-push" in sys.argv
    force_commit = "--force" in sys.argv
    force_loc = "--force-loc" in sys.argv

    # 1. Cálculos de tiempo
    uptime = calculate_uptime(today)
    age = calculate_age(today)
    print(f"⏱️  Uptime calculado : {uptime}")
    print(f"🎂  Age calculada    : {age}")

    # 2. Métricas de GitHub
    print(f"\n📡 Consultando métricas de GitHub (@{USER_NAME})...")
    stats = get_github_stats(USER_NAME, ACCESS_TOKEN)
    loc_stats = get_saved_loc()

    print(f"   • Contribuciones : {stats['contribs']:,}")
    print(f"   • Repositorios   : {stats['repos']:,}")
    print(f"   • Estrellas      : {stats['stars']:,}")
    print(f"   • Líneas Código  : +{loc_stats.get('additions', 0):,} / -{loc_stats.get('deletions', 0):,}")

    variables = {
        "uptime": uptime,
        "age": age,
        "contribs": f"{stats['contribs']:,}",
        "repos": f"{stats['repos']:,}",
        "stars": f"{stats['stars']:,}",
        "addlines": f"{loc_stats['additions']:,}",
        "additions": f"{loc_stats['additions']:,}",
        "deletedlines": f"{loc_stats['deletions']:,}",
        "deletions": f"{loc_stats['deletions']:,}",
    }

    if dry_run:
        print("\n🔍 Modo --dry-run activo: No se aplicaron cambios ni commits.")
        return

    # 3. Generar SVG desde template.txt
    print(f"\n🎨 Generando {os.path.relpath(SVG_PATH, BASE_DIR)} desde template.txt...")
    changed = generate_svg_from_template(TEMPLATE_PATH, SVG_PATH, variables)
    if changed:
        print("  [✓] SVG generado con éxito con diseño vectorial ultra ligero (~5 KB).")
    else:
        print("  [*] El archivo SVG ya estaba al día.")

    # 4. Flujo Git
    if changed or force_commit:
        print("\n📦 Gestionando Git...")
        perform_git_workflow(uptime, age, stats, push=(not no_push))
    else:
        print("\n✨ Nada que commitear hoy. Tu perfil está al 100% al día.")

    print("\n=======================================================")
    print(" 🎉 Proceso finalizado.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()