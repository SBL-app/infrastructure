# Processus de mise à jour des dépendances — SBL

> Référence : compétence **C4.1.1** — *Gérer les mises à jour des dépendances et des bibliothèques tiers, en surveillant régulièrement les nouvelles versions, en évaluant les impacts des mises à jour, et en les intégrant de manière sécurisée pour maintenir l'application à jour et sécurisée.*

---

## 1. Périmètre logiciel concerné

Le projet repose sur quatre dépôts aux écosystèmes distincts. Le périmètre couvert est exhaustif : aucune couche de la pile n'est laissée hors surveillance.

| Dépôt | Écosystème | Volume | Exemples de dépendances |
|---|---|---|---|
| `api` | Composer (PHP 8.3) | ~25 directes | Symfony 7.3, Doctrine ORM 3, LexikJWT, Monolog |
| `api` | Docker | 1 image | `php:8.4-fpm-alpine` |
| `SBL-app` | npm (Node 20) | ~15 directes | Vue 3.4, Vite, Pinia, Vue Router, Ky |
| `SBL-app` | Docker | 2 images | `node:20-alpine`, `nginx:alpine` |
| `bot` | npm (Node 20) | 3 directes | discord.js 14, node-cron |
| `bot` | Docker | 1 image | `node:20-alpine` |
| `infrastructure` | Docker | 4 images | Traefik v3, PostgreSQL 16, Nginx, Uptime Kuma |
| Tous | GitHub Actions | ~8 actions | `actions/checkout`, `softprops/action-gh-release` |

---

## 2. Fréquence des mises à jour

| Nature | Fréquence | Justification |
|---|---|---|
| **Correctifs de sécurité** | Immédiate, à la publication de l'avis | GitHub Security Advisories notifie sans attendre le cycle hebdomadaire |
| **Dépendances applicatives** (Composer, npm) | Hebdomadaire, lundi 08:00 | Le lundi matin permet de traiter les mises à jour en début de semaine et de disposer de plusieurs jours d'observation avant le week-end, période de forte activité de la ligue |
| **Images Docker** | Hebdomadaire, lundi 08:00 | Aligné sur les dépendances applicatives : une reconstruction d'image est de toute façon nécessaire |
| **Actions GitHub** | Mensuelle | Périmètre CI uniquement, sans impact sur la production |
| **Versions majeures** | À la demande, planifiées | Exclues du flux automatique (voir section 4) |

Le choix du lundi matin n'est pas neutre. Les matchs de la ligue se déroulent en soirée et le week-end : y déployer une mise à jour de dépendance exposerait les utilisateurs à une régression au pire moment. Le début de semaine laisse au contraire une fenêtre de plusieurs jours pour détecter un problème avant la période de forte affluence.

---

## 3. Type de mise à jour : automatique ou manuel

Le processus est **hybride**, et cette combinaison est délibérée.

| Étape | Mode | Outil |
|---|---|---|
| Surveillance des nouvelles versions | **Automatique** | Dependabot |
| Ouverture de la pull request | **Automatique** | Dependabot |
| Exécution des tests et du lint | **Automatique** | GitHub Actions |
| Analyse d'impact et relecture | **Manuel** | Développeur |
| Fusion | **Manuel** | Développeur |
| Déploiement | **Manuel** | `docker compose build && up -d` |

**Pourquoi aucune fusion automatique ?** L'argument en faveur de l'auto-merge sur les correctifs est réel : il réduit la charge de maintenance et raccourcit la fenêtre d'exposition aux vulnérabilités. Il a néanmoins été écarté ici pour une raison tenant au contexte du projet — SBL est maintenu par une seule personne et sert une ligue en activité. Une régression fusionnée automatiquement un lundi matin pourrait rester non détectée plusieurs jours, alors qu'aucune astreinte n'existe. Le délai de revue manuelle (24 à 48 h en pratique) reste très inférieur au coût d'une indisponibilité non surveillée.

La suite de tests PHPUnit (unitaires, intégration, fonctionnels) constitue le filet de sécurité automatisé : une pull request Dependabot dont la CI échoue est fermée sans analyse supplémentaire.

---

## 4. Évaluation de l'impact

### 4.1 Grille de décision

| Type d'incrément | Traitement | Vérification exigée |
|---|---|---|
| **Correctif** (`1.2.3 → 1.2.4`) | Flux automatique, revue rapide | CI au vert |
| **Mineur** (`1.2.0 → 1.3.0`) | Flux automatique, revue attentive | CI au vert + lecture du journal amont |
| **Majeur** (`1.x → 2.x`) | **Exclu du flux automatique** | Analyse dédiée, test manuel, planification |
| **Avis de sécurité** | Traitement prioritaire | Évaluation de l'exploitabilité réelle |

Les versions majeures sont explicitement exclues dans les quatre fichiers `dependabot.yml` (`ignore: version-update:semver-major`). Une montée majeure implique des ruptures de compatibilité documentées, souvent une migration de code : c'est une tâche de planification, pas une pull request hebdomadaire à relire entre deux développements. Elles sont traitées lors des jalons du projet, avec du temps dédié.

### 4.2 Regroupement des mises à jour

Les dépendances fortement couplées sont regroupées en une pull request unique :

| Groupe | Dépôt | Motif du regroupement |
|---|---|---|
| `symfony` | api | Les composants Symfony s'exigent mutuellement en versions compatibles ; les mettre à jour séparément produit des pull requests bloquées en attente les unes des autres |
| `doctrine` | api | Même couplage entre ORM, DBAL et bundles |
| `vue` | SBL-app | Runtime, router et store partagent des définitions de types |
| `build` | SBL-app | Vite et ses plugins suivent un cycle de version commun |
| `dev-tools` | tous | Aucun impact en production, regroupés pour limiter le bruit |

À l'inverse, **discord.js n'est jamais regroupé**. Cette bibliothèque suit les évolutions de l'API Discord, qui déprécie régulièrement des endpoints avec un préavis court. Chaque mise à jour justifie la lecture du journal de versions amont avant fusion.

### 4.3 Points de vigilance spécifiques

**PostgreSQL** — un changement de version majeure impose une migration du répertoire de données (`pg_upgrade` ou sauvegarde/restauration). Le conteneur refuse de démarrer sur un répertoire créé par une version antérieure. Toute montée est donc conditionnée à une sauvegarde préalable vérifiée.

**PHP** — l'image de base conditionne la compatibilité des extensions compilées (`pdo_pgsql`, `intl`, `gmp`). Une montée de version mineure de PHP exige de vérifier que les extensions se compilent toujours dans le `Dockerfile`.

**Traefik** — la configuration passe par des labels Docker dont la syntaxe a changé entre les versions majeures. L'épinglage sur `traefik:v3` protège contre une bascule involontaire vers v4.

---

## 5. Intégration sécurisée

Le circuit d'une mise à jour, de sa détection à sa mise en production :

```
Dependabot détecte une nouvelle version
        │
        ▼
Pull request automatique sur la branche dev
        │
        ▼
CI : PHPUnit (unit + intégration + fonctionnel), lint PHP
        │
        ├── Échec ──► Fermeture de la PR, analyse si récurrent
        │
        ▼ Succès
Revue manuelle : lecture du journal de versions amont
        │
        ▼
Fusion sur dev  ──►  Vérification manuelle en local
        │
        ▼
Fusion sur main  ──►  Release (tag SemVer + CHANGELOG)
        │
        ▼
docker compose build && up -d
        │
        ▼
Contrôle post-déploiement : /api/health + sondes Uptime Kuma
```

Le contrôle post-déploiement ferme la boucle avec le système de supervision : une mise à jour de dépendance ayant cassé la connectivité base ou l'exécution des migrations est détectée en moins d'une minute par la sonde `/api/health`, sans attendre qu'un utilisateur le signale.

---

## 6. Historique et efficacité du dispositif

Dependabot était déjà partiellement actif sur le projet avant cette formalisation, et a produit des résultats concrets :

| Date | Mise à jour | Nature |
|---|---|---|
| 28/12/2025 | `js-yaml` 3.x → 4.1.1 (bot) | Correction d'une alerte de sécurité |
| 27/12/2025 | `symfony/http-foundation` 7.3.0 → 7.4.1 | Correctif de sécurité |
| 02/02/2026 | `symfony/process` 7.3.0 → 7.4.5 | Correctif de sécurité |

Ces trois interventions ont toutes été déclenchées par une détection automatique, aucune n'aurait été identifiée par une veille manuelle. Elles confirment l'intérêt du dispositif tout en soulignant sa limite initiale : la configuration était implicite, non documentée et incomplète (le frontend et l'infrastructure n'étaient pas couverts). La formalisation décrite ici étend le périmètre aux quatre dépôts et à l'ensemble des écosystèmes.

---

## 7. Mise en œuvre

Les fichiers de configuration sont en place dans chaque dépôt :

```
api/.github/dependabot.yml              Composer + Docker + Actions
SBL-app/.github/dependabot.yml          npm + Docker + Actions
bot/.github/dependabot.yml              npm + Docker + Actions
infrastructure/.github/dependabot.yml   Docker + Actions
```

Activation côté GitHub, pour chaque dépôt : *Settings → Code security → Dependency graph*, puis *Dependabot alerts* et *Dependabot security updates*. Le fichier `dependabot.yml` est pris en compte automatiquement dès sa présence sur la branche par défaut.
