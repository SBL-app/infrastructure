# Mise en route du dispositif de maintien en condition opérationnelle

Ce document est la checklist d'activation de ce qui a été implémenté, ainsi que le tableau de correspondance avec la grille d'évaluation du Bloc 4.

---

## 1. Ce qui a été livré

| Fichier | Rôle |
|---|---|
| `api/src/Controller/HealthController.php` | Endpoint `/api/health` — sonde applicative (base, migrations, version) |
| `api/tests/Functional/Controller/HealthControllerTest.php` | Tests protégeant le contrat consommé par la sonde |
| `api/src/Monolog/DiscordWebhookHandler.php` | Handler Monolog de collecte des erreurs vers Discord |
| `api/config/packages/monolog.yaml` | Chaîne de handlers : buffer → déduplication → Discord |
| `api/config/services.yaml` | Déclaration du handler et des paramètres de supervision |
| `api/Dockerfile` | Injection de `APP_VERSION` / `APP_COMMIT` au build |
| `docker-compose.yml` | Service `uptime-kuma`, variables de version et de heartbeat |
| `bot/monitoring/heartbeat.js` | Sonde push du bot Discord |
| `bot/main.js` | Démarrage du heartbeat au `ready` |
| `api/.github/ISSUE_TEMPLATE/bug_report.yml` | **Fiche de consignation d'anomalie** |
| `api/.github/ISSUE_TEMPLATE/feature_request.yml` | Demande d'évolution |
| `api/CHANGELOG.md` | Journal de versions : 5 reconstituées + 3 tags réels sur `main` |
| `api/cliff.toml` | Configuration de génération automatique du journal |
| `api/.github/workflows/release.yml` | Workflow de release (tag + changelog + release GitHub) |
| `*/.github/dependabot.yml` | Mise à jour des dépendances, 4 dépôts |
| `docker/backup/` | Service de sauvegarde : dump, vérification, rotation, restauration |
| `docker-compose.yml` | Service `backup` et variables de sauvegarde |
| `docs/SAUVEGARDE.md` | Stratégie de sauvegarde et procédure de restauration testée |
| `docs/SUPERVISION.md` | Documentation du système de supervision |
| `docs/PROCESSUS_ANOMALIES.md` | Documentation du processus de collecte |
| `docs/JOURNAL_VERSIONS.md` | Documentation du versionnage et des releases |
| `docs/MISE_A_JOUR_DEPENDANCES.md` | Documentation du processus de mise à jour |

---

## 2. Checklist d'activation

### Étape 1 — Dependabot (≈ 10 min, aucun déploiement)

- [ ] Committer et pousser les quatre `.github/dependabot.yml` sur la branche par défaut de chaque dépôt
- [ ] Pour chaque dépôt : *Settings → Code security* → activer *Dependency graph*, *Dependabot alerts*, *Dependabot security updates*
- [ ] Créer les labels utilisés : `type:deps`, `composant:api`, `composant:front`, `composant:bot`, `composant:infra`
- [ ] **Capture à conserver** : la liste des pull requests Dependabot ouvertes après le premier passage

### Étape 2 — Templates d'issue (≈ 10 min)

- [ ] Pousser `api/.github/ISSUE_TEMPLATE/` sur la branche par défaut
- [ ] Créer les labels : `type:bug`, `type:feature`, `severite:s1` à `s4`, `statut:a-trier`, `statut:confirme`, `statut:non-reproductible`, `statut:en-cours`, `statut:en-recette`
- [ ] Renseigner l'URL Discord réelle dans `config.yml`
- [ ] **Capture à conserver** : le formulaire de création d'issue tel qu'il s'affiche sur GitHub

### Étape 3 — Endpoint de santé (≈ 15 min)

- [ ] `docker compose build api && docker compose up -d api`
- [ ] Vérifier : `curl -s https://<API_DOMAIN>/api/health | jq`
- [ ] Vérifier le cas dégradé : `docker compose stop postgres`, rappeler l'endpoint, attendre un code 503, puis redémarrer
- [ ] **Capture à conserver** : les deux réponses JSON (nominale et dégradée)

### Étape 4 — Uptime Kuma (≈ 1 h 30)

- [ ] Renseigner `MONITORING_DOMAIN` dans `.env` et pointer le DNS vers le VPS
- [ ] `docker compose up -d uptime-kuma`
- [ ] Créer le compte administrateur
- [ ] Créer le webhook Discord sur `#alertes-technique` et l'enregistrer comme notification
- [ ] Créer les six sondes décrites dans `docs/SUPERVISION.md` §3
- [ ] Récupérer le token de la sonde *Push*, le reporter dans `UPTIME_KUMA_PUSH_URL`
- [ ] `docker compose up -d bot` et vérifier dans les journaux : `[heartbeat] Supervision active`
- [ ] Créer la status page publique
- [ ] **Captures à conserver** : tableau de bord des six sondes, status page, configuration d'une sonde

### Étape 5 — Test réel de la chaîne d'alerte (≈ 30 min)

C'est l'étape à ne pas sacrifier : elle produit la preuve la plus convaincante du dispositif, et elle alimente simultanément la section « traitement d'une anomalie » du dossier.

- [ ] `docker compose stop api`
- [ ] Attendre l'alerte dans `#alertes-technique` (≈ 3 min)
- [ ] **Captures à conserver** : la notification Discord, le graphe de la sonde passant au rouge
- [ ] `docker compose start api`
- [ ] **Capture à conserver** : la notification de résolution

### Étape 6 — Journal de versions (≈ 45 min)

- [ ] Relire `api/CHANGELOG.md` et corriger les libellés qui ne correspondraient pas à ton souvenir des jalons
- [ ] Créer le tag de départ : `git tag -a v1.0.0 -m "Release v1.0.0" && git push --tags`
- [ ] Créer la release GitHub correspondante en y collant la section `v1.0.0` du changelog
- [ ] Déclencher le workflow *Release* en mode `patch` pour valider l'automatisation
- [ ] **Captures à conserver** : la page des releases GitHub, une release avec ses notes, le workflow réussi

### Étape 7 — Sauvegarde automatisée de PostgreSQL (≈ 45 min)

- [ ] Renseigner les variables `TZ`, `BACKUP_*` dans `.env` (voir `.env.example`)
- [ ] Créer dans Uptime Kuma une sonde *Push* dédiée, intervalle **93 600 s (26 h)**, notification Discord rattachée
- [ ] Reporter le token dans `BACKUP_UPTIME_KUMA_PUSH_URL`
- [ ] `docker compose up -d --build backup`
- [ ] Déclencher une sauvegarde : `docker compose exec backup backup.sh`
- [ ] Rejouer la restauration de contrôle : `docker compose exec backup restore.sh --latest`
- [ ] Provoquer un échec (`docker compose stop postgres`) et vérifier l'alerte Discord
- [ ] **Captures à conserver** : la sortie complète d'une sauvegarde vérifiée, la sortie de la restauration, l'alerte Discord d'échec, la sonde de sauvegarde dans Uptime Kuma

---

## 3. Correspondance avec la grille d'évaluation

| Compétence | Élim. | Livrable attendu | Éléments produits |
|---|---|---|---|
| **C4.1.1** — Mises à jour des dépendances | | Description du processus | `docs/MISE_A_JOUR_DEPENDANCES.md` : fréquence (§2), périmètre logiciel (§1), type automatique/manuel (§3) — les trois critères de la grille |
| **C4.1.2** — Système de supervision | ⚠️ | Description du système | `docs/SUPERVISION.md` : périmètre adapté à la typologie (§1), six sondes et leur finalité (§3), critères qualité/performance (§4), surveillance de disponibilité (§3.1, §3.2) |
| **C4.2.1** — Consignation des anomalies | ⚠️ | Processus + fiche de consignation | `docs/PROCESSUS_ANOMALIES.md` (§2 collecte, §3 triage) et `bug_report.yml` : champs de reproduction obligatoires, analyse et préconisation (§4) |
| **C4.2.2** — Créer et déployer un correctif | | Traitement d'une anomalie | À produire depuis l'étape 5 : chaîne alerte → issue → correctif → CI/CD → déploiement |
| **C4.3.1** — Axes d'amélioration | | Recommandations argumentées | À rédiger — s'appuyer sur les métriques Uptime Kuma (section 4 ci-dessous) |
| **C4.3.2** — Journal des versions | ⚠️ | Exemplaire du journal | `api/CHANGELOG.md` (9 versions, dont 3 tags réels) et `docs/JOURNAL_VERSIONS.md` : correctifs documentés et reliés aux issues (§4) |
| **C4.3.3** — Collaboration support client | | Problème résolu avec le support | À rédiger — traiter le staff SBL comme partie prenante support |

**Les trois compétences éliminatoires sont désormais couvertes par des éléments concrets et vérifiables.**

---

## 4. Ce qui reste à ta main pour le dossier

Trois sections ne peuvent pas être générées : elles reposent sur ton vécu du projet.

**C4.2.2 — Traitement d'une anomalie.** L'étape 5 en fournit le squelette, mais une anomalie réelle issue de l'historique serait plus convaincante. Deux candidates identifiées dans l'historique Git : la correction du calcul de `totalGames` dans le pourcentage d'avancement (23/10/2024) et la fuite de clé privée (14/03/2026, avec un angle sécurité intéressant).

**C4.3.1 — Recommandations d'amélioration.** La grille exige des recommandations argumentées en coût et délai, réalistes, et renforçant l'attractivité. La première piste identifiée — la sauvegarde automatisée de PostgreSQL — est désormais **implémentée** (`docs/SAUVEGARDE.md`) : elle peut être présentée comme une recommandation formulée puis mise en œuvre, ce qui est plus convaincant qu'une simple préconisation. Sa limite résiduelle, documentée en §8, fournit d'ailleurs la recommandation suivante : externalisation chiffrée des dumps hors du VPS. Restent deux pistes : mise en cache des endpoints de classement (les métriques Uptime Kuma fourniront les temps de réponse pour chiffrer le gain) et environnement de pré-production (le déploiement se fait actuellement directement en production).

**C4.3.3 — Collaboration support client.** Le staff SBL joue le rôle de support de premier niveau : il reçoit les remontées des joueurs, les qualifie, et te les transmet. Cette répartition est exactement ce que la grille attend sous le terme « contribution des différentes parties prenantes ». Un cas concret issu des points mensuels fera l'affaire.
