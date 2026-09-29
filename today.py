#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Daily Profile & SVG Updater (today.py)
 Emanuel Lopez F (ema28pro)
-----------------------------------------------------------------------------
 - Calcula de forma dinámica Uptime (desde mayo 2022) y Edad (28/nov/2005).
 - Obtiene estadísticas en vivo de GitHub (contribuciones, repos, estrellas).
 - Actualiza con precisión el SVG neofetch (img/CodeMe.svg) preservando estilos.
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
# CÁLCULOS TEMPORALES
# =============================================================================
def calculate_uptime(today: datetime.date) -> str:
    """
    Calcula los años transcurridos desde UPTIME_START con un decimal.
    Ejemplo: '4.4'
    """
    days = (today - UPTIME_START).days
    years = round(days / 365.25, 1)
    return f"{years}"


def calculate_age(today: datetime.date) -> str:
    """
    Calcula la edad en años completos.
    Si hoy es el día del cumpleaños, agrega un emoji de pastel 🎂.
    Ejemplo: '20 years' o '21 years 🎂'
    """
    diff = relativedelta.relativedelta(today, BIRTHDAY)
    years = diff.years
    is_birthday = (diff.months == 0 and diff.days == 0)
    suffix = " 🎂" if is_birthday else ""
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
    - followers: seguidores
    """
    stats = {
        "contribs": 0,
        "repos": 0,
        "stars": 0,
        "followers": 0,
    }

    # 1. Datos básicos del usuario (repos públicos, followers)
    headers = {"User-Agent": f"today-script-{username}"}
    if token:
        headers["Authorization"] = f"token {token}"

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

    # 3. Contribuciones del último año (mediante scraping de la página de contribuciones oficial o GraphQL)
    if token:
        # Modo GraphQL con token
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

    # Fallback sin token
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
    - Línea 4: Uptime y Age
    - Línea 7: GitHub.Stats (Contribs, Repos, Stars)
    Retorna True si el archivo fue modificado exitosamente.
    """
    if not os.path.exists(svg_path):
        raise FileNotFoundError(f"No se encontró el archivo SVG en: {svg_path}")

    with open(svg_path, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Actualizar número de Uptime (ej. 2.4 -> 4.4)
    uptime_regex = r'(>Uptime</span>\s*<span[^>]*class="cm-operator"[^>]*>:\s*</span>\s*<span[^>]*>[^<]*</span>\s*<span[^>]*class="cm-number"[^>]*>)([^<]+)(</span>)'
    content, c_up = re.subn(uptime_regex, rf"\g<1>{uptime_str}\g<3>", content, count=1)

    # 2. Actualizar Age en comentarios
    age_regex = r'(#Age:\s*</span>\s*<span[^>]*class="cm-comment"[^>]*>\s*</span>\s*<span[^>]*class="cm-comment"[^>]*>)([^<]+)(</span>)(?:\s*<span[^>]*class="cm-comment"[^>]*>[^<]*</span>)?'
    content, c_age = re.subn(age_regex, rf"\g<1>{age_str}\g<3>", content, count=1)

    # 3. Insertar o actualizar bloque GitHub.Stats en línea 7
    gh_block_regex = r'<span id="github-stats-block"[^>]*>.*?</span><!-- /gh-stats -->'
    contribs = stats.get("contribs", 0)
    repos = stats.get("repos", 0)
    stars = stats.get("stars", 0)

    gh_block = (
        f'<span id="github-stats-block">'
        f'<span class="cm-identifier" style="color: rgb(201, 209, 217);">GitHub.Stats</span>'
        f'<span class="cm-operator" style="color: rgb(201, 209, 217);">: </span>'
        f'<span class="cm-number" style="color: rgb(201, 209, 217);">{contribs:,}</span> '
        f'<span class="cm-identifier" style="color: rgb(201, 209, 217);">Contribs</span>'
        f'<span class="cm-punctuation" style="color: rgb(201, 209, 217);">, </span>'
        f'<span class="cm-number" style="color: rgb(201, 209, 217);">{repos:,}</span> '
        f'<span class="cm-identifier" style="color: rgb(201, 209, 217);">Repos</span>'
        f'<span class="cm-punctuation" style="color: rgb(201, 209, 217);">, </span>'
        f'<span class="cm-number" style="color: rgb(201, 209, 217);">{stars:,}</span> '
        f'<span class="cm-identifier" style="color: rgb(201, 209, 217);">Stars</span>'
        f'</span><!-- /gh-stats -->'
    )

    if re.search(gh_block_regex, content):
        content, c_gh = re.subn(gh_block_regex, gh_block, content, count=1)
    else:
        # Inserción en la línea 7 tras el arte ASCII ($RMM!)
        pattern_l7 = r'(\$RMM</span>\s*<span[^>]*class="cm-operator"[^>]*>!</span>\s*<span[^>]*>[^<]*</span>)'
        match = re.search(pattern_l7, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + gh_block + content[insert_pos:]
            c_gh = 1
        else:
            c_gh = 0

    if c_up == 0 or c_age == 0 or c_gh == 0:
        print(f"  [!] Alerta de reemplazo: Uptime={c_up}, Age={c_age}, GitHub.Stats={c_gh}")

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
        f"[Uptime: {uptime_str}y, Age: {age_str}, {stats.get('contribs', 0)} contribs]"
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
    print(f"⏱️  Uptime calculado : {uptime} years (desde mayo 2022)")
    print(f"🎂  Age calculada    : {age} (nacimiento 28/nov/2005)")

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
        print("  [✓] SVG actualizado correctamente con nuevos valores.")
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