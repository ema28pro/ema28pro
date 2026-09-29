#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Daily Profile & SVG Updater (today.py)
 Emanuel Lopez F (ema28pro)
-----------------------------------------------------------------------------
 - Calcula dinámicamente Uptime y Age con años, meses y días (estilo pyoneer).
 - Muestra métricas de GitHub en vivo al lado de "Contact:".
 - Actualiza lenguajes y herramientas según el stack actual.
 - Realiza git add, git commit automático y git push a GitHub.
=============================================================================
"""

import sys
import os
import re
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
# CONFIGURACIÓN PERSONALIZABLE
# =============================================================================
USER_NAME = os.environ.get("GITHUB_USER", "ema28pro")
BIRTHDAY = datetime.date(2005, 11, 28)       # 28 de Noviembre de 2005
UPTIME_START = datetime.date(2022, 5, 1)      # Mayo de 2022

# Ruta al archivo SVG principal
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_PATH = os.path.join(BASE_DIR, "img", "CodeMe.svg")

# Token opcional (si existe en el entorno o archivo .env, permite GraphQL extendido)
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")


# =============================================================================
# CÁLCULOS TEMPORALES (ESTILO PYONEER / ANDREW6RANT)
# =============================================================================
def format_unit(val: int, unit: str) -> str:
    """Retorna número y unidad formateada con plural según corresponda."""
    return f"{val} {unit}{'s' if val != 1 else ''}"


def get_time_string(start_date: datetime.date, end_date: datetime.date) -> str:
    """
    Retorna la duración exacta entre dos fechas en formato:
    'X years, Y months, Z days'
    """
    diff = relativedelta.relativedelta(end_date, start_date)
    parts = []
    if diff.years > 0:
        parts.append(format_unit(diff.years, "year"))
    if diff.months > 0:
        parts.append(format_unit(diff.months, "month"))
    if diff.days > 0 or not parts:
        parts.append(format_unit(diff.days, "day"))
    return ", ".join(parts)


def calculate_uptime(today: datetime.date) -> str:
    """Calcula Uptime en años, meses y días desde mayo 2022."""
    return get_time_string(UPTIME_START, today)


def calculate_age(today: datetime.date) -> str:
    """
    Calcula edad en años, meses y días desde 28/nov/2005.
    Si hoy es el día del cumpleaños, agrega un emoji de pastel 🎂.
    """
    diff = relativedelta.relativedelta(today, BIRTHDAY)
    age_str = get_time_string(BIRTHDAY, today)
    if diff.months == 0 and diff.days == 0:
        age_str += " 🎂"
    return age_str


# =============================================================================
# RECOLECCIÓN DE MÉTRICAS DE GITHUB
# =============================================================================
def get_github_stats(username: str, token: str = None) -> dict:
    """
    Obtiene las estadísticas de GitHub del usuario:
    - contribs: total de contribuciones (último año o histórico)
    - repos: total de repositorios públicos
    - stars: total de estrellas recibidas en repositorios
    - followers: seguidores
    """
    stats = {
        "contribs": 0,
        "repos": 0,
        "stars": 0,
        "followers": 0,
    }

    headers = {"User-Agent": f"today-script-{username}"}
    if token:
        headers["Authorization"] = f"token {token}"

    # 1. Datos básicos del usuario (repos públicos, followers)
    try:
        user_url = f"https://api.github.com/users/{username}"
        res = requests.get(user_url, headers=headers, timeout=10)
        if res.status_code == 200:
            user_data = res.json()
            stats["repos"] = user_data.get("public_repos", 0)
            stats["followers"] = user_data.get("followers", 0)
    except Exception as e:
        print(f"  [!] Advertencia al obtener datos de usuario: {e}")

    # 2. Conteo de estrellas en todos los repositorios públicos
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


# =============================================================================
# ACTUALIZACIÓN DEL ARCHIVO SVG
# =============================================================================
def update_svg_file(svg_path: str, uptime_str: str, age_str: str, stats: dict) -> bool:
    """
    Actualiza con precisión milimétrica las líneas de CodeMe.svg:
    - Línea 4: Uptime y Age con años, meses y días
    - Línea 7: Se mantiene limpia (sin estadísticas atravesadas)
    - Línea 8: Languages.Programming sin (Learning) y con JavaScript
    - Línea 11: Tools.Frontend con React y Tailwind
    - Línea 12: Tools.Backend con PostgreSQL
    - Línea 17: Estadísticas de GitHub al lado de "Contact:"
    Retorna True si el archivo fue modificado exitosamente.
    """
    if not os.path.exists(svg_path):
        raise FileNotFoundError(f"No se encontró el archivo SVG en: {svg_path}")

    with open(svg_path, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Limpieza de línea 7 (remover cualquier bloque previo de stats atravesadas)
    content = re.sub(r'<span id="github-stats-block"[^>]*>.*?</span><!-- /gh-stats -->', '', content)

    # 2. Actualizar stack tecnológico en el código
    # Languages.Programming: agregar JavaScript y quitar (Learning)
    content = content.replace("Python, Java, C/C++ (Learning)", "Python, Java, C/C++, JavaScript")
    # Tools.Frontend: React sin (Learning) y agregar Tailwind
    content = content.replace("HTML, CSS, JS, React (Learning)", "HTML, CSS, JS, React, Tailwind")
    # Tools.Backend: cambiar MongoDB por PostgreSQL
    content = content.replace(">MongoDB<", ">PostgreSQL<")

    # 3. Línea 4: Uptime y Age con formato completo (años, meses y días)
    sample_style = 'color: rgb(201, 209, 217);'
    line4_pattern = r'(>Uptime</span>\s*<span[^>]*class="cm-operator"[^>]*>:\s*</span>)(.*?)(</pre>)'
    new_line4_body = (
        f'<span style="{sample_style}"> </span>'
        f'<span class="cm-number" style="{sample_style}">{uptime_str}</span>'
        f'<span style="{sample_style}"> </span>'
        f'<span class="cm-comment" style="{sample_style}">#Age: {age_str}</span></span>'
    )
    content = re.sub(line4_pattern, rf"\g<1>{new_line4_body}\g<3>", content, count=1)

    # 4. Línea 17: Mostrar estadísticas al lado de Contact:
    content = re.sub(r'<span id="contact-stats-block"[^>]*>.*?</span><!-- /contact-stats -->', '', content)

    contribs = stats.get("contribs", 0)
    repos = stats.get("repos", 0)
    stars = stats.get("stars", 0)

    contact_pattern = r'(>Contact</span>\s*<span[^>]*class="cm-operator"[^>]*>:\s*</span>)'
    stats_html = (
        f'<span id="contact-stats-block">'
        f'<span style="{sample_style}">  </span>'
        f'<span class="cm-identifier" style="{sample_style}">GitHub</span>'
        f'<span class="cm-operator" style="{sample_style}">: </span>'
        f'<span class="cm-number" style="{sample_style}">{contribs:,}</span> '
        f'<span class="cm-identifier" style="{sample_style}">Contribs</span>'
        f'<span class="cm-punctuation" style="{sample_style}">, </span>'
        f'<span class="cm-number" style="{sample_style}">{repos:,}</span> '
        f'<span class="cm-identifier" style="{sample_style}">Repos</span>'
        f'<span class="cm-punctuation" style="{sample_style}">, </span>'
        f'<span class="cm-number" style="{sample_style}">{stars:,}</span> '
        f'<span class="cm-identifier" style="{sample_style}">Stars</span>'
        f'</span><!-- /contact-stats -->'
    )
    content = re.sub(contact_pattern, rf"\g<1>{stats_html}", content, count=1)

    if content != original_content:
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(content)
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
    # 1. Comprobar si hay cambios pendientes en img/CodeMe.svg o el repo
    status_proc = run_git(["status", "--porcelain", "img/CodeMe.svg"])
    has_changes = bool(status_proc.stdout.strip())

    if not has_changes:
        print("  [*] No hay cambios nuevos en img/CodeMe.svg (ya estaba al día).")
        return False

    # 2. git add
    print("  [+] Ejecutando: git add img/CodeMe.svg today.py daily.ps1")
    run_git(["add", "img/CodeMe.svg", "today.py", "daily.ps1"])

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

    # Parámetros CLI
    dry_run = "--dry-run" in sys.argv
    no_push = "--no-push" in sys.argv
    force_commit = "--force" in sys.argv

    # 1. Cálculos de tiempo
    uptime = calculate_uptime(today)
    age = calculate_age(today)
    print(f"⏱️  Uptime calculado : {uptime}")
    print(f"🎂  Age calculada    : {age}")

    # 2. Obtener estadísticas de GitHub
    print(f"\n📡 Consultando métricas de GitHub (@{USER_NAME})...")
    stats = get_github_stats(USER_NAME, ACCESS_TOKEN)
    print(f"   • Contribuciones : {stats['contribs']:,}")
    print(f"   • Repositorios   : {stats['repos']:,}")
    print(f"   • Estrellas      : {stats['stars']:,}")
    print(f"   • Seguidores     : {stats['followers']:,}")

    if dry_run:
        print("\n🔍 Modo --dry-run activo: No se aplicaron cambios ni commits.")
        return

    # 3. Actualizar SVG
    print(f"\n🎨 Actualizando {os.path.relpath(SVG_PATH, BASE_DIR)}...")
    changed = update_svg_file(SVG_PATH, uptime, age, stats)
    if changed:
        print("  [✓] SVG actualizado correctamente con nuevos valores y nuevo layout.")
    else:
        print("  [*] El archivo SVG ya contenía los valores actuales.")

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