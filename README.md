# SBL — Infrastructure

Déploiement de la stack **Splatton Baguette League** : reverse-proxy Traefik
(HTTPS Let's Encrypt), base PostgreSQL, API Symfony, frontend Vue et bot Discord,
le tout orchestré par Docker Compose avec des réseaux isolés.

## Architecture

| Service       | Rôle                                              | Réseau            |
| ------------- | ------------------------------------------------- | ----------------- |
| `traefik`     | Reverse proxy, TLS automatique                    | `web`             |
| `postgres`    | Base de données                                   | `internal`        |
| `api`         | API Symfony (PHP-FPM)                             | `internal`        |
| `api-nginx`   | Serveur web de l'API                              | `web`, `internal` |
| `frontend`    | Application Vue (build statique servi par Nginx)  | `web`             |
| `bot`         | Bot Discord (isolé, sans port exposé)             | `bot-network`     |
| `bot-gateway` | Passerelle bot → API                              | `internal`, `bot-network` |
| `bot-notify-relay` | Relais API → bot (`POST /notify` uniquement) | `internal`, `bot-network` |

Le réseau `internal` est marqué `internal: true` : la base et l'API ne sont
donc jamais joignables directement depuis Internet.

## Prérequis

- Docker Engine 24+ et le plugin Docker Compose v2
- Les dépôts `api`, `SBL-app` et `bot` présents dans des sous-dossiers du même
  nom (ils servent de contexte de build), ou des images pré-construites.

## Configuration

Copier `.env.example` vers `.env` et renseigner les valeurs. **Le fichier `.env`
n'est jamais commité** (voir `.gitignore`).

```bash
cp .env.example .env
$EDITOR .env
```

### Notifications API → bot

L'API notifie le bot via `bot-notify-relay`, qui ne proxifie que `POST /notify`
vers `bot:3001` (404 sinon). Le bot n'a toujours aucun port publié et reste hors
du réseau `internal`. Variables à poser dans `.env` :

| Variable                 | Usage                                                        |
| ------------------------ | ------------------------------------------------------------ |
| `DISCORD_BOT_NOTIFY_KEY` | Clé partagée API ↔ bot (génération : `openssl rand -hex 32`) |
| `FRONTEND_URL`           | Déjà présente ; transmise au bot sous le nom `FRONT_URL`      |

`DISCORD_BOT_NOTIFY_URL` (`http://bot-notify-relay/notify`) et `NOTIFY_PORT`
(`3001`) sont fixés dans `docker-compose.yml`.

## Démarrage local

```bash
docker compose config      # valide le fichier
docker compose up -d       # démarre la stack
docker compose logs -f     # suit les logs
```

## Base de données

Le schéma initial est fourni dans `migration_postgres.sql` :

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < migration_postgres.sql
```

## Intégration & déploiement continus

- **CI** (`.github/workflows/ci.yml`) — à chaque push / PR :
  - `yamllint` sur tous les fichiers YAML,
  - `actionlint` sur les workflows,
  - `docker compose config` (validation de la stack),
  - application de `migration_postgres.sql` sur une base PostgreSQL jetable.
- **CD** (`.github/workflows/cd.yml`) — à chaque push sur `main` : synchronisation
  des fichiers vers le serveur via SSH puis `docker compose up -d`.

### Secrets requis pour le CD

| Secret        | Description                                            |
| ------------- | ------------------------------------------------------ |
| `SSH_HOST`    | Hôte du serveur de production                          |
| `SSH_USER`    | Utilisateur SSH autorisé à lancer Docker              |
| `SSH_KEY`     | Clé privée SSH (format PEM)                            |
| `SSH_PORT`    | Port SSH (optionnel, défaut `22`)                     |
| `DEPLOY_PATH` | Chemin absolu de la stack sur le serveur (ex `/opt/sbl`) |

Le serveur doit contenir le fichier `.env` de production à la racine de
`DEPLOY_PATH` (il n'est pas synchronisé par le CD).
