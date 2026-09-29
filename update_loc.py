#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
 Calculate Lines of Code (update_loc.py)
 Emanuel Lopez F (ema28pro)
-----------------------------------------------------------------------------
 Script independiente para calcular el total histórico de líneas agregadas (++)
 y eliminadas (--) en todos tus repositorios de GitHub mediante GraphQL.
 Guarda el resultado en 'loc.json' para que 'today.py' lo lea al instante.
=============================================================================
"""

import os
import json
import datetime
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOC_FILE = os.path.join(BASE_DIR, "loc.json")

def load_dotenv(filepath: str = None):
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

def calculate_all_loc(username: str, token: str):
    if not token:
        print("[!] Error: No se encontró ACCESS_TOKEN en .env ni en el entorno.")
        return None

    headers = {"Authorization": f"token {token}"}

    print(f"\n📡 Conectando a GitHub GraphQL (@{username})...")
    
    # 1. Obtener ID de usuario y lista de repositorios
    u_query = """query($login: String!) {
      user(login: $login) {
        id
        repositories(first: 100, ownerAffiliations: [OWNER]) {
          nodes { name }
        }
      }
    }"""
    r = requests.post("https://api.github.com/graphql", json={"query": u_query, "variables": {"login": username}}, headers=headers, timeout=15)
    if r.status_code != 200:
        print(f"[!] Error al consultar usuario ({r.status_code}): {r.text}")
        return None

    u_data = r.json()["data"]["user"]
    user_id = u_data["id"]
    repo_names = [repo["name"] for repo in u_data["repositories"]["nodes"]]
    print(f"   • Repositorios encontrados: {len(repo_names)}")

    total_adds = 0
    total_dels = 0
    total_commits = 0

    repo_query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100) {
                nodes {
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

    for i, name in enumerate(repo_names, start=1):
        print(f"   [{i}/{len(repo_names)}] Analizando {name}...", end="\r", flush=True)
        try:
            rr = requests.post("https://api.github.com/graphql", json={"query": repo_query, "variables": {"owner": username, "name": name}}, headers=headers, timeout=10)
            if rr.status_code == 200:
                repo_obj = rr.json().get("data", {}).get("repository")
                if repo_obj and repo_obj.get("defaultBranchRef"):
                    commits = repo_obj["defaultBranchRef"]["target"]["history"]["nodes"]
                    for c in commits:
                        u = c.get("author", {}).get("user")
                        if u and u.get("id") == user_id:
                            total_commits += 1
                            total_adds += c.get("additions", 0)
                            total_dels += c.get("deletions", 0)
        except Exception as e:
            pass

    print()
    data = {
        "updated": datetime.date.today().strftime("%Y-%m-%d"),
        "additions": total_adds,
        "deletions": total_dels,
        "commits": total_commits,
    }

    with open(LOC_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"\n[✓] ¡Cálculo completado y guardado en {os.path.basename(LOC_FILE)}!")
    print(f"   • Commits analizados : {total_commits:,}")
    print(f"   • Líneas agregadas   : +{total_adds:,}")
    print(f"   • Líneas eliminadas  : -{total_dels:,}\n")
    return data

if __name__ == "__main__":
    calculate_all_loc(USER_NAME, ACCESS_TOKEN)
