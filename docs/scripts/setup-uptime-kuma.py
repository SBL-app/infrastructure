#!/usr/bin/env python3
"""Configuration du dispositif de supervision SBL dans Uptime Kuma.

L'interface d'Uptime Kuma ne s'automatise pas en ligne de commande, mais son
API socket.io est pilotable par la bibliothèque `uptime-kuma-api`. Ce script
crée l'intégralité du dispositif décrit dans docs/SUPERVISION.md §3 à §5 :

  1. la notification Discord vers le canal #alertes-technique ;
  2. les six sondes de la section 3, avec leurs seuils ;
  3. le rattachement de la notification à chacune ;
  4. la status page publique (frontend, API, bot) ;
  5. l'affichage du token de la sonde push, à reporter dans le .env.

Le script est **idempotent** : une sonde dont le nom existe déjà est laissée
en l'état plutôt que dupliquée. Il peut donc être relancé sans dommage après
une interruption.

Aucun secret n'est écrit en dur. Les identifiants Uptime Kuma et l'URL du
webhook proviennent de l'environnement ; les paramètres de la base et les
domaines sont lus dans le fichier .env de production.

Usage :

    export KUMA_USERNAME='...'
    export KUMA_PASSWORD='...'
    export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
    python3 setup-uptime-kuma.py

Variables facultatives :

    KUMA_URL        URL de l'instance (défaut : https://status.baguette-league.eu)
    SBL_ENV_FILE    Fichier .env de production (défaut : /opt/sbl/.env)
    DRY_RUN=1       Affiche ce qui serait créé, sans rien écrire
"""

import os
import sys

try:
    from uptime_kuma_api import (
        UptimeKumaApi,
        MonitorType,
        NotificationType,
        DockerType,
        UptimeKumaException,
    )
except ImportError:
    sys.exit(
        "La bibliothèque uptime-kuma-api est absente.\n"
        "    python3 -m venv .venv && ./.venv/bin/pip install uptime-kuma-api"
    )

# --------------------------------------------------------------------------
# Paramètres du dispositif — voir docs/SUPERVISION.md §3 et §4
# --------------------------------------------------------------------------

# Conteneurs surveillés par la sonde Docker (§3.6).
#
# `sbl-scheduler` est volontairement absent : le service `scheduler` n'est pas
# publié sur la branche `main` du dépôt d'infrastructure et le conteneur
# n'existe donc pas en production. L'inscrire ici produirait une sonde rouge en
# permanence, donc un flux d'alertes ininterrompu — exactement la fatigue
# d'alerte que §4 cherche à éviter. À réintroduire le jour où le service est
# déployé.
DOCKER_CONTAINERS = ["sbl-api", "sbl-postgres", "sbl-frontend", "sbl-bot"]

# Seuil de préavis d'expiration du certificat TLS, en jours (§3.5).
TLS_EXPIRY_NOTIFY_DAYS = [14]

STATUS_PAGE_SLUG = "sbl"
STATUS_PAGE_TITLE = "SBL — État des services"

NOTIFICATION_NAME = "Discord — #alertes-technique"


def read_env_file(path):
    """Lit un fichier .env sans dépendance externe.

    Volontairement minimaliste : on ne gère que `CLE=valeur`, ce que produit le
    fichier de production. Les guillemets encadrants sont retirés.
    """
    values = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("'\"")
    except FileNotFoundError:
        sys.exit(f"Fichier .env introuvable : {path}")
    return values


def require(name, value, hint=""):
    if not value:
        sys.exit(f"Variable manquante : {name}. {hint}".rstrip())
    return value


def main():
    kuma_url = os.environ.get("KUMA_URL", "https://status.baguette-league.eu")
    username = require("KUMA_USERNAME", os.environ.get("KUMA_USERNAME"))
    password = require("KUMA_PASSWORD", os.environ.get("KUMA_PASSWORD"))
    webhook = require(
        "DISCORD_WEBHOOK_URL",
        os.environ.get("DISCORD_WEBHOOK_URL"),
        "URL du webhook du canal #alertes-technique.",
    )
    env_path = os.environ.get("SBL_ENV_FILE", "/opt/sbl/.env")
    dry_run = os.environ.get("DRY_RUN") == "1"

    env = read_env_file(env_path)
    frontend_domain = require(
        "FRONTEND_DOMAIN", env.get("FRONTEND_DOMAIN"), f"Attendu dans {env_path}."
    )
    pg_user = env.get("POSTGRES_USER", "sbl")
    pg_db = env.get("POSTGRES_DB", "sbl")
    pg_password = require(
        "POSTGRES_PASSWORD", env.get("POSTGRES_PASSWORD"), f"Attendu dans {env_path}."
    )

    if dry_run:
        print("DRY_RUN : aucune écriture ne sera effectuée.\n")

    print(f"Connexion à {kuma_url} …")
    api = UptimeKumaApi(kuma_url, timeout=30)
    try:
        api.login(username, password)
        print("  authentifié.\n")
        configure(
            api,
            dry_run=dry_run,
            webhook=webhook,
            password=password,
            frontend_domain=frontend_domain,
            pg_user=pg_user,
            pg_password=pg_password,
            pg_db=pg_db,
        )
    finally:
        api.disconnect()


def configure(api, *, dry_run, webhook, password, frontend_domain,
              pg_user, pg_password, pg_db):
    # --- 1. Notification Discord (§5.1) -----------------------------------
    existing_notifications = {n["name"]: n["id"] for n in api.get_notifications()}

    if NOTIFICATION_NAME in existing_notifications:
        notification_id = existing_notifications[NOTIFICATION_NAME]
        print(f"= notification « {NOTIFICATION_NAME} » déjà présente (id {notification_id})")
    elif dry_run:
        notification_id = 0
        print(f"+ notification « {NOTIFICATION_NAME} » (Discord)")
    else:
        result = api.add_notification(
            name=NOTIFICATION_NAME,
            type=NotificationType.DISCORD,
            isDefault=False,
            # Appliquée à toutes les sondes créées ci-dessous, y compris les
            # sondes Docker : une alerte muette n'a aucune valeur.
            applyExisting=False,
            discordWebhookUrl=webhook,
            discordUsername="Uptime Kuma — SBL",
        )
        notification_id = result["id"]
        print(f"+ notification « {NOTIFICATION_NAME} » créée (id {notification_id})")

    notifications = [notification_id] if notification_id else []

    # --- 2. Hôte Docker pour les sondes de conteneur (§3.6) ----------------
    existing_hosts = {h["name"]: h["id"] for h in api.get_docker_hosts()}
    host_name = "VPS SBL (socket local)"

    if host_name in existing_hosts:
        docker_host_id = existing_hosts[host_name]
        print(f"= hôte Docker « {host_name} » déjà présent (id {docker_host_id})")
    elif dry_run:
        docker_host_id = 0
        print(f"+ hôte Docker « {host_name} »")
    else:
        result = api.add_docker_host(
            name=host_name,
            dockerType=DockerType.SOCKET,
            dockerDaemon="/var/run/docker.sock",
        )
        docker_host_id = result["id"]
        print(f"+ hôte Docker « {host_name} » créé (id {docker_host_id})")

    print()

    # --- 3. Les six sondes de la section 3 --------------------------------
    monitors = []

    # §3.1 — Frontend. La recherche du mot-clé « SBL » dans le corps de la
    # réponse distingue l'application réellement servie d'un Nginx ayant perdu
    # ses fichiers statiques, qui répond 200 sur une page vide.
    # §3.5 — le contrôle d'expiration du certificat est porté par cette sonde.
    monitors.append(dict(
        type=MonitorType.KEYWORD,
        name="Frontend — application Vue",
        url=f"https://{frontend_domain}",
        keyword="SBL",
        interval=60,
        maxretries=3,
        retryInterval=60,
        expiryNotification=True,
        notificationIDList=notifications,
    ))

    # §3.2 — API. Sondée sur le réseau interne : on mesure la santé réelle du
    # service, pas celle du reverse proxy. /api/health vérifie la connectivité
    # PostgreSQL et l'état des migrations Doctrine, ce qui couvre le
    # déploiement dont le code est à jour mais dont les migrations ont échoué.
    monitors.append(dict(
        type=MonitorType.JSON_QUERY,
        name="API — /api/health",
        url="http://api-nginx/api/health",
        jsonPath="$.status",
        expectedValue="ok",
        interval=60,
        maxretries=3,
        retryInterval=60,
        notificationIDList=notifications,
    ))

    # §3.3 — PostgreSQL. Sert au diagnostic différentiel : rouge en même temps
    # que l'API, la cause est la base ; verte, la cause est applicative.
    # Intervalle plus long (120 s) pour ne pas ouvrir de connexions inutiles.
    monitors.append(dict(
        type=MonitorType.POSTGRES,
        name="PostgreSQL — connexion",
        databaseConnectionString=(
            f"postgres://{pg_user}:{pg_password}@postgres:5432/{pg_db}"
        ),
        interval=120,
        maxretries=2,
        retryInterval=120,
        notificationIDList=notifications,
    ))

    # §3.4 — Bot Discord. Sonde push : le bot n'accepte aucune connexion
    # entrante. L'intervalle de 120 s est la période de grâce — deux cycles
    # d'émission manqués (60 s) déclenchent l'alerte.
    monitors.append(dict(
        type=MonitorType.PUSH,
        name="Bot Discord — heartbeat",
        interval=120,
        maxretries=0,
        retryInterval=120,
        notificationIDList=notifications,
    ))

    # §3.6 — Conteneurs. Un conteneur en `restart: unless-stopped` qui plante
    # et redémarre en boucle répond normalement aux sondes HTTP entre deux
    # redémarrages : seule la sonde de conteneur le révèle.
    for container in DOCKER_CONTAINERS:
        monitors.append(dict(
            type=MonitorType.DOCKER,
            name=f"Conteneur — {container}",
            docker_container=container,
            docker_host=docker_host_id,
            interval=60,
            maxretries=2,
            retryInterval=60,
            notificationIDList=notifications,
        ))

    existing_monitors = {m["name"]: m for m in api.get_monitors()}
    created = {}

    for spec in monitors:
        name = spec["name"]
        if name in existing_monitors:
            created[name] = existing_monitors[name]["id"]
            print(f"= sonde « {name} » déjà présente (id {created[name]})")
            continue
        if dry_run:
            print(f"+ sonde « {name} » ({spec['type']})")
            continue
        try:
            result = api.add_monitor(**spec)
            created[name] = result["monitorID"]
            print(f"+ sonde « {name} » créée (id {created[name]})")
        except UptimeKumaException as error:
            print(f"! sonde « {name} » — échec : {error}", file=sys.stderr)

    print()

    # --- 4. Seuil d'expiration du certificat TLS (§3.5) --------------------
    if dry_run:
        print(f"+ préavis d'expiration TLS : {TLS_EXPIRY_NOTIFY_DAYS} jours")
    else:
        try:
            api.set_settings(password=password, tlsExpiryNotifyDays=TLS_EXPIRY_NOTIFY_DAYS)
            print(f"+ préavis d'expiration TLS réglé à {TLS_EXPIRY_NOTIFY_DAYS} jours")
        except UptimeKumaException as error:
            print(f"! préavis TLS — échec : {error}", file=sys.stderr)

    # --- 5. Status page publique (§5.4) -----------------------------------
    public_names = [
        "Frontend — application Vue",
        "API — /api/health",
        "Bot Discord — heartbeat",
    ]
    public_ids = [created[n] for n in public_names if n in created]

    existing_pages = {p["slug"] for p in api.get_status_pages()}
    if dry_run:
        print(f"+ status page « /{STATUS_PAGE_SLUG} » avec {len(public_ids)} sondes")
    else:
        try:
            if STATUS_PAGE_SLUG not in existing_pages:
                api.add_status_page(STATUS_PAGE_SLUG, STATUS_PAGE_TITLE)
            api.save_status_page(
                slug=STATUS_PAGE_SLUG,
                title=STATUS_PAGE_TITLE,
                description=(
                    "Disponibilité des services de la Symfony Baguette League. "
                    "Historique sur 90 jours."
                ),
                published=True,
                showPoweredBy=False,
                showCertificateExpiry=True,
                publicGroupList=[{
                    "name": "Services",
                    "weight": 1,
                    "monitorList": [{"id": i} for i in public_ids],
                }],
            )
            print(f"+ status page publique : /{STATUS_PAGE_SLUG} ({len(public_ids)} sondes)")
        except UptimeKumaException as error:
            print(f"! status page — échec : {error}", file=sys.stderr)

    # --- 6. Token de la sonde push ----------------------------------------
    print()
    push_id = created.get("Bot Discord — heartbeat")
    if dry_run or not push_id:
        print("Token de la sonde push : disponible après création réelle.")
        return

    token = api.get_monitor(push_id).get("pushToken")
    if not token:
        print("! token de la sonde push introuvable — à relever dans l'interface.",
              file=sys.stderr)
        return

    print("=" * 68)
    print("Ligne à reporter dans le .env de production, puis `docker compose up -d bot` :")
    print()
    print(f"  UPTIME_KUMA_PUSH_URL=http://uptime-kuma:3001/api/push/{token}")
    print()
    print("=" * 68)


if __name__ == "__main__":
    main()
