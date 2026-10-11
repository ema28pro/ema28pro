#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Calculate Lines of Code (update_loc.py)
 Emanuel Lopez F (ema28pro)
-----------------------------------------------------------------------------
 Calcula el total histórico de líneas agregadas (++) y eliminadas (--) en
 todos tus repositorios de GitHub mediante GraphQL.

 Enfoque incremental (cacheado en '.loc_cache.json', local y no versionado):
 - Guarda el acumulado por repositorio y el SHA del último commit procesado
   (HEAD del branch por defecto).
 - En cada ejecución recorre SOLO los commits nuevos (de HEAD hacia atrás
   hasta encontrar el SHA cacheado) y suma las líneas hechas por ti.
 - Si el historial fue reescrito (rebase/force-push) y el SHA cacheado ya no
   existe, se recalcula ese repositorio desde cero automáticamente.
 - Excluye merge commits (2+ padres) para no atribuirte líneas de otras ramas.
 - Solo cuenta commits cuyo autor (author.user) eres tú.

 El total agregado se guarda en 'loc.json' para que 'today.py' lo lea al
 instante. Usa --rebuild para ignorar la caché y recalcular todo desde cero.

 Limitaciones conocidas (precisión de las métricas de LOC):
 - Solo se recorre el branch POR DEFECTO de cada repositorio.
 - Los commits cuyo email no está vinculado a tu cuenta de GitHub no suman
   (author.user == null), aunque sean tuyos.
 - Se cuenta el tamaño completo de cada commit: archivos generados/vendidos
   (package-lock.json, node_modules, datasets, binarios) pueden inflar el total.
 - Cuenta TODOS los repos que posees (públicos y privados, incl. forks):
   el mismo universo que el conteo de repositorios de today.py.
=============================================================================
"""

import os
import sys
import json
import datetime
import time
import requests

# Configurar salida UTF-8 en terminales de Windows (evita UnicodeEncodeError)
if sys.platform.startswith("win"):
    try:
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOC_FILE = os.path.join(BASE_DIR, "loc.json")
CACHE_FILE = os.path.join(BASE_DIR, ".loc_cache.json")


def load_dotenv(filepath=None):
    if filepath is None:
        filepath = os.path.join(BASE_DIR, ".env")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


load_dotenv()

USER_NAME = os.environ.get("GITHUB_USER", "ema28pro")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")

GQL_URL = "https://api.github.com/graphql"

# Lista de repositorios propiedad del usuario + SHA del HEAD del branch por defecto
REPOS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    id
    repositories(first: 100, after: $after, ownerAffiliations: [OWNER]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        defaultBranchRef { target { ... on Commit { oid } } }
      }
    }
  }
}"""

# Historial paginado del branch por defecto
HISTORY_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              oid
              parents(first: 2) { totalCount }
              author { user { id } }
              additions
              deletions
            }
          }
        }
      }
    }
  }
}"""


# =============================================================================
# CACHÉ LOCAL
# =============================================================================
def load_cache() -> dict:
    """Lee el acumulado por repositorio desde .loc_cache.json."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                repos = data.get("repos")
                if isinstance(repos, dict):
                    return repos
        except Exception as e:
            print(f"[!] No se pudo leer {os.path.basename(CACHE_FILE)}: {e}")
    return {}


def save_cache(repos: dict):
    """Guarda el acumulado por repositorio en .loc_cache.json."""
    data = {
        "updated": datetime.date.today().strftime("%Y-%m-%d"),
        "repos": repos,
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)


# =============================================================================
# GITHUB GRAPHQL
# =============================================================================
def gql(query: str, variables: dict, headers: dict, retries: int = 4) -> dict:
    """
    Ejecuta una consulta GraphQL con reintentos y backoff exponencial ante
    fallos transitorios (timeouts, 5xx, rate limit). Lanza excepción si todos
    los intentos fallan.
    """
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(GQL_URL, json={"query": query, "variables": variables}, headers=headers, timeout=30)
        except requests.RequestException as e:
            last_err = e
            wait = 2 ** attempt
            print(f"\n   [!] Conexión GraphQL falló ({e}). Reintento {attempt + 1}/{retries} en {wait}s...")
            time.sleep(wait)
            continue

        rate_limited = r.status_code == 403 and "rate limit" in r.text.lower()
        if r.status_code in (429, 502, 503, 504) or r.status_code >= 500 or rate_limited:
            last_err = RuntimeError(f"HTTP {r.status_code}")
            wait = 2 ** attempt
            print(f"\n   [!] GitHub respondió {r.status_code}. Reintento {attempt + 1}/{retries} en {wait}s...")
            time.sleep(wait)
            continue

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

        payload = r.json()
        if "errors" in payload:
            raise RuntimeError(str(payload["errors"])[:300])
        return payload.get("data", {})

    raise last_err if last_err else RuntimeError("GraphQL: fallo desconocido")


def get_owned_repos(username: str, headers: dict):
    """Devuelve (user_id, [{name, head_oid}]) de todos los repos propiedad del usuario."""
    user_id = None
    repos = []
    cursor = None
    while True:
        data = gql(REPOS_QUERY, {"login": username, "after": cursor}, headers)
        user = data.get("user")
        if not user:
            break
        user_id = user.get("id")
        conn = user.get("repositories") or {}
        for node in conn.get("nodes", []):
            target = ((node.get("defaultBranchRef") or {}).get("target")) or {}
            repos.append({"name": node.get("name"), "head": target.get("oid")})
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage") or not page.get("endCursor"):
            break
        cursor = page.get("endCursor")
    return user_id, repos


def count_commits(username: str, headers: dict, user_id: str, name: str, stop_sha: str):
    """
    Recorre el branch por defecto desde HEAD hacia atrás, deteniéndose al
    encontrar `stop_sha` (el último commit ya procesado).

    Devuelve (adds, dels, commits, status), donde status es:
    - "matched": se encontró stop_sha -> conteo incremental válido.
    - "full":    se recorrió TODO el historial sin error -> conteo completo válido
                 (repo nuevo o historial reescrito).
    - "error":   falló a mitad de camino -> conteo parcial NO fiable (no usar).
    """
    adds = dels = n = 0
    cursor = None
    while True:
        try:
            data = gql(HISTORY_QUERY, {"owner": username, "name": name, "cursor": cursor}, headers)
        except Exception as e:
            print(f"\n   [!] {name}: {e}")
            return adds, dels, n, "error"

        repo = data.get("repository")
        if not repo or not repo.get("defaultBranchRef"):
            return adds, dels, n, "error"
        history = ((repo["defaultBranchRef"] or {}).get("target") or {}).get("history")
        if not history:
            return adds, dels, n, "error"

        for c in history.get("nodes", []):
            if stop_sha and c.get("oid") == stop_sha:
                return adds, dels, n, "matched"
            # Excluir merge commits (2+ padres): evitan atribuirte líneas de otras ramas
            if ((c.get("parents") or {}).get("totalCount", 0)) > 1:
                continue
            u = (c.get("author") or {}).get("user")
            if u and u.get("id") == user_id:
                n += 1
                adds += c.get("additions", 0)
                dels += c.get("deletions", 0)

        page = history.get("pageInfo") or {}
        if not page.get("hasNextPage") or not page.get("endCursor"):
            return adds, dels, n, "full"
        cursor = page.get("endCursor")


# =============================================================================
# CÁLCULO PRINCIPAL
# =============================================================================
def calculate_all_loc(username: str, token: str, rebuild: bool = False):
    if not token:
        print("[!] Error: No se encontró ACCESS_TOKEN en .env ni en el entorno.")
        return None

    headers = {"Authorization": f"token {token}"}

    print(f"\n[+] Conectando a GitHub GraphQL (@{username})...")

    cache = {} if rebuild else load_cache()
    if rebuild:
        print("   • Modo --rebuild: se ignora la caché y se recalcula todo.")
    elif cache:
        print(f"   • Caché local: {len(cache)} repositorios guardados.")
    else:
        print("   • Caché local vacía: se hará el cálculo inicial completo.")

    try:
        user_id, repos = get_owned_repos(username, headers)
    except Exception as e:
        print(f"[!] Error consultando repositorios (se conserva la caché): {e}")
        return None
    if not user_id:
        print("[!] No se pudo obtener el usuario.")
        return None
    print(f"   • Repositorios encontrados: {len(repos)}")

    results = {}
    errors = 0
    for i, repo in enumerate(repos, start=1):
        name = repo["name"]
        head = repo["head"]
        print(f"   [{i}/{len(repos)}] Analizando {name}...", end="\r", flush=True)

        prev = cache.get(name)
        if not head:
            # Repositorio vacío (sin branch por defecto): conservar lo cacheado
            results[name] = prev or {"sha": None, "additions": 0, "deletions": 0, "commits": 0}
            continue

        stop_sha = prev.get("sha") if prev else None
        adds, dels, n, status = count_commits(username, headers, user_id, name, stop_sha)

        if status == "error":
            # Conteo parcial NO fiable: no pisar el acumulado bueno.
            # Se reintenta el delta en la próxima ejecución.
            errors += 1
            if prev:
                results[name] = prev
            else:
                # Sin caché previa: dejar en cero y sha=None para forzar el recálculo luego
                results[name] = {"sha": None, "additions": 0, "deletions": 0, "commits": 0}
        elif status == "matched" and prev:
            # Incremental: se suma lo nuevo a lo ya acumulado
            results[name] = {
                "sha": head,
                "additions": prev.get("additions", 0) + adds,
                "deletions": prev.get("deletions", 0) + dels,
                "commits": prev.get("commits", 0) + n,
            }
        else:
            # "full": repo nuevo o historial reescrito -> reemplaza con el conteo completo
            results[name] = {"sha": head, "additions": adds, "deletions": dels, "commits": n}

    print()
    total_adds = sum(e.get("additions", 0) for e in results.values())
    total_dels = sum(e.get("deletions", 0) for e in results.values())
    total_commits = sum(e.get("commits", 0) for e in results.values())

    data = {
        "updated": datetime.date.today().strftime("%Y-%m-%d"),
        "additions": total_adds,
        "deletions": total_dels,
        "commits": total_commits,
    }

    with open(LOC_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    save_cache(results)

    if errors:
        print(f"\n[!] Atención: {errors} repositorio(s) fallaron y conservaron su valor previo.")
        print("    No se perdieron datos; se reintentará su delta en la próxima ejecución.")

    print(f"\n[OK] ¡Cálculo completado y guardado en {os.path.basename(LOC_FILE)}!")
    print(f"   • Repositorios       : {len(results):,}")
    print(f"   • Commits analizados : {total_commits:,}")
    print(f"   • Líneas agregadas   : +{total_adds:,}")
    print(f"   • Líneas eliminadas  : -{total_dels:,}")
    print(f"   • Caché por repo     : {os.path.basename(CACHE_FILE)}\n")
    return data


if __name__ == "__main__":
    calculate_all_loc(USER_NAME, ACCESS_TOKEN, rebuild="--rebuild" in sys.argv)
