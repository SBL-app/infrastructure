# Recommandations d'amélioration — SBL

> Référence : compétence **C4.3.1** — *Élaborer des recommandations d'amélioration et d'évolution du logiciel en identifiant les axes de progrès sur la base des indicateurs de suivi et des anomalies constatées, afin d'améliorer la performance du logiciel et de renforcer son attractivité.*

---

## 1. Méthode et cadre de chiffrage

### 1.1 Contraintes du projet

Toute recommandation formulée ici est contrainte par quatre paramètres qui ne sont pas négociables et qui écartent d'emblée une large part des « bonnes pratiques » génériques :

| Contrainte | Conséquence sur les recommandations |
|---|---|
| **Équipe d'une personne** | Aucune mesure ne peut reposer sur une revue croisée ou une astreinte. Tout ce qui est manuel et répétitif sera abandonné au bout de trois semaines : seule l'automatisation tient dans la durée. |
| **VPS unique, 2 Go de RAM** | Pas de redondance, pas de cluster, pas de service annexe gourmand. Chaque conteneur ajouté se paie sur la mémoire disponible de PostgreSQL et de PHP-FPM. |
| **Budget quasi nul** | Le dépôt est public : les minutes GitHub Actions sont gratuites et sans quota. Toute dépense récurrente doit rester sous quelques euros par mois pour être acceptable. |
| **Ligue amateur, ≈ 24 équipes** | Le volume de données est faible. Les gains de performance ne se justifient donc pas par la charge actuelle mais par la **marge de croissance** et par le temps de développement économisé. |

Une cinquième contrainte, structurelle, motive à elle seule deux des recommandations : **le déploiement se fait directement en production**, sans environnement intermédiaire (`PROCEDURE_DEPLOIEMENT.md` § « Mise à jour de l'application » : `git pull` → `docker compose up -d --build` → `doctrine:migrations:migrate`). Il n'existe aujourd'hui aucune barrière automatique entre un commit et les utilisateurs.

### 1.2 Base de mesure

Les indicateurs de référence sont ceux définis dans `docs/SUPERVISION.md` § 4. Ils constituent le socle sur lequel l'effet de chaque recommandation devra être vérifié :

| Indicateur (SUPERVISION § 4) | Cible | Seuil d'alerte | Recommandations concernées |
|---|---|---|---|
| Disponibilité mensuelle frontend / API | ≥ 99 % | < 99 % | R1, R4 |
| Temps de réponse `/api/health` | < 300 ms | > 1000 ms | R2, R3 |
| Latence PostgreSQL | < 50 ms | > 200 ms | R2, R3 |
| Migrations en attente | 0 | ≥ 1 | R4 |
| Latence websocket Discord | < 200 ms | > 500 ms | — |
| Expiration certificat TLS | > 30 j | < 14 j | — |

Trois indicateurs complémentaires sont proposés ici, car les précédents ne mesurent que la disponibilité et pas la qualité du cycle de livraison :

| Indicateur proposé | Définition | Valeur actuelle | Source |
|---|---|---|---|
| **Régressions détectées avant production** | Tests en échec bloquant une fusion, sur le total des régressions constatées | **0 %** — aucun test n'est exécuté automatiquement | `api/.github/workflows/` |
| **Couverture de tests** | Lignes de `src/` couvertes par la suite | **non mesurable en l'état** | absence de PCOV/Xdebug dans l'image (`api/Dockerfile`) |
| **Délai de détection d'un défaut de déploiement** | Écart entre le déploiement et la détection | ≈ intervalle de sonde (3 min) *si* la panne est franche ; indéterminé sinon | `docs/SUPERVISION.md` § 3.2 |

### 1.3 Convention de chiffrage

- **Coût en jours-homme** : temps de développement effectif, tests et documentation inclus, pour le développeur du projet — c'est-à-dire quelqu'un qui connaît déjà le code. Les fourchettes données correspondent à une hypothèse basse et à une hypothèse haute, pas à une moyenne.
- **Coût financier** : dépense externe récurrente uniquement. Le temps du développeur n'est pas facturé sur ce projet ; à titre de **comparaison indicative seulement**, une journée valorisée au tarif d'un développeur indépendant confirmé se situe autour de 400 € HT. Cette valorisation n'est jamais additionnée au coût financier réel dans les tableaux, pour ne pas laisser croire à un décaissement.
- **Honnêteté sur les mesures** : chaque chiffre est étiqueté **mesuré**, **modélisé** ou **estimé**. Les incertitudes sont regroupées en § 8.

---

## 2. R1 — Exécuter la suite de tests en intégration continue

**Priorité : 1 (prérequis aux autres).**

### 2.1 Constat, avec preuve

Le projet dispose d'une suite de tests substantielle : **345 tests** répartis en 188 tests unitaires, 22 tests d'intégration et 135 tests fonctionnels (`api/tests/`). Elle a coûté un effort réel de conception, avec une classe de base outillée (`tests/Functional/ApiTestCase.php`) et une séparation propre en trois suites (`api/phpunit.xml.dist`).

**Cette suite n'est exécutée par aucun automatisme.** Le dépôt `api` comporte trois workflows GitHub Actions et aucun ne lance PHPUnit :

| Workflow | Déclencheur | Ce qu'il fait |
|---|---|---|
| `claude-code-review.yml` | ouverture / mise à jour de PR | relecture assistée par IA |
| `claude.yml` | mention `@claude` | assistance à la demande |
| `release.yml` | manuel | calcul de version, génération du changelog, publication |

Il n'existe donc **aucune barrière automatique** entre un commit et la production. La conséquence est immédiatement vérifiable : au 18/08/2026, sur l'arbre de travail courant de la branche `dev` du dépôt `api`, **13 tests sur 345 échouent** :

```
1) AuthControllerTest::testLoginSuccess
2) AuthControllerTest::testVerifyTokenMissingToken
3) AuthControllerTest::testRefreshTokenMissingToken
4) AuthControllerTest::testLoginAndVerifyTokenWorkflow
5) AuthControllerTest::testEmptyRequestBody
6) AuthControllerTest::testInvalidJsonRequestBody
7) DivisionControllerTest::testGetDivisionBySeasonEmpty
8) PlayerControllerTest::testCreatePlayer
9) PlayerControllerTest::testUpdatePlayer
10) PlayerControllerTest::testUpdatePlayerNotFound
11) PlayerControllerTest::testDeletePlayer
12) PlayerControllerTest::testDeletePlayerNotFound
13) SeasonControllerTest::testGetSeasonCompletion
```

Ces échecs ne sont pas des tests obsolètes : l'analyse du journal `var/log/test.log` montre qu'au moins six d'entre eux révèlent un **défaut réel affectant la production**. L'écouteur `src/EventListener/ApiProblemExceptionListener.php` est enregistré avec la priorité 10, donc **avant** l'écouteur de sécurité de Symfony qui convertit `AccessDeniedException` en réponse HTTP 403. Or `AccessDeniedException` n'implémente pas `HttpExceptionInterface` : elle tombe dans la branche par défaut de l'écouteur (lignes 40-52) et produit une réponse **500 Internal Server Error**.

Autrement dit : **un appel API non autorisé renvoie aujourd'hui une erreur serveur au lieu d'un refus d'accès.** Le client ne peut pas distinguer « vous n'avez pas le droit » de « le serveur est en panne », et cette erreur alimente Sentry comme un incident applicatif. La suite de tests détecte ce défaut depuis toujours ; personne ne le voit, parce que personne ne lance la suite.

Deux constats aggravants complètent le tableau :

- **La couverture n'est pas mesurable.** La cible `make test-coverage` existe et invoque `phpunit --coverage-html`, mais l'image Docker (`api/Dockerfile`, lignes 4-20) n'installe ni PCOV ni Xdebug, et aucune de ces extensions n'est disponible en local. La commande ne peut produire aucun rapport.
- **Des zones sensibles n'ont aucun test dédié.** En croisant `src/` et `tests/` : `MatchProposalController` (13,8 ko, l'un des plus gros contrôleurs du projet), `UserController`, `AuthenticationService`, `DiscordOAuthService`, `PushNotificationService`, ainsi que `ApiAccessVoter`, `ApiAuthenticator` et `ApiSecurityListener` — c'est-à-dire **l'essentiel de la couche d'autorisation** — ne sont couverts par aucun test qui leur soit propre.

### 2.2 Solution proposée

1. **Un workflow `tests.yml`** déclenché sur chaque `push` et chaque `pull_request` : installation PHP 8.4 + PCOV, `composer install`, génération des clés JWT de test, `php bin/phpunit` sur les trois suites, publication du taux de couverture en résumé de job.
2. **Deux vérifications complémentaires dans le même workflow**, très peu coûteuses : `make lint` (syntaxe PHP, déjà écrit) et `composer audit` (vulnérabilités connues des dépendances, déjà utilisé par `make security`).
3. **Protection de branche** sur `dev` et `main` : fusion interdite si le workflow échoue. C'est cette étape, et non le workflow lui-même, qui transforme un indicateur en garde-fou.
4. **Correction des 13 échecs** — en premier lieu le mappage `AccessDeniedException` → 403 dans `ApiProblemExceptionListener`, qui à lui seul devrait en résoudre la majorité.
5. **Optionnel (0,5 j)** : accélérer la suite. `ApiTestCase::setUp()` supprime et recrée l'intégralité du schéma SQLite **avant chacun des 135 tests fonctionnels** (`tests/Functional/ApiTestCase.php`, lignes 39-50). C'est la cause principale des **4 min 55 s** que dure aujourd'hui la suite complète (mesuré). Remplacer la recréation par une transaction annulée en `tearDown` ramènerait cette durée à moins d'une minute.

### 2.3 Gain attendu

| Effet | Chiffrage | Nature |
|---|---|---|
| Régressions détectées avant production | de **0 %** à **~100 % de celles couvertes par les 345 tests** | mesuré (le nombre de tests est connu) |
| Défauts existants révélés immédiatement | **13**, dont au moins 1 affectant la production (500 au lieu de 403) | mesuré |
| Couverture de tests | de « non mesurable » à **valeur publiée à chaque commit** | mesuré |
| Temps de vérification manuelle avant déploiement | ≈ 15 min par déploiement → **0** | estimé |
| Durée de la suite (si l'option § 2.2.5 est retenue) | 4 min 55 s → **< 1 min** | modélisé |

Le gain de délai est le plus important et le plus difficile à chiffrer : détecter une régression au moment du commit plutôt qu'après un signalement du staff SBL fait passer le cycle de correction de plusieurs jours à quelques minutes. Sur les 13 défauts actuels, le délai de détection est déjà supérieur à plusieurs mois.

### 2.4 Coûts, risque, attractivité

| | |
|---|---|
| **Coût en jours-homme** | **1,5 à 2,5 j** — 0,5 j pour le workflow et la protection de branche, 1 à 2 j pour corriger les 13 échecs (dont la durée dépend de ce qu'ils révèlent), 0,5 j en option pour l'accélération de la suite |
| **Coût financier** | **0 €** — le dépôt `SBL-app/api` est public, les minutes GitHub Actions sont gratuites et illimitées dans ce cas |
| **Risque** | **Faible.** Le seul effet de bord est un frein volontaire au rythme de fusion. Risque résiduel identifié : une suite instable (*flaky*) découragerait l'usage du garde-fou ; les tests fonctionnels reposant sur SQLite alors que la production utilise PostgreSQL, un test peut passer en CI et échouer en production — limite assumée, traitée par R4 |
| **Effet sur l'attractivité** | Indirect mais déterminant. Un utilisateur ne quitte pas une application parce qu'elle est lente, il la quitte parce qu'elle est imprévisible. Corriger le 500-au-lieu-de-403 rend par ailleurs les messages d'erreur de l'interface compréhensibles, ce qui est directement perceptible par le staff |

---

## 3. R2 — Supprimer les requêtes N+1 des endpoints de classement

**Priorité : 2 (après R1, qui en fournit le filet de sécurité).**

### 3.1 Constat, avec preuve

Les endpoints de classement construisent leurs réponses en interrogeant la base **une fois par équipe**, à l'intérieur d'une boucle. Le code est explicite :

- `api/src/Controller/DivisionController.php:228-229` (`GET /api/divisions/{id}/details`) — pour chaque `TeamStat`, un `$teamRepository->find()` puis un `$playerRepository->findBy(['team' => …])` ;
- `api/src/Controller/DivisionController.php:134-135` (`GET /api/divisions/{id}/teams`) — même schéma ;
- `api/src/Controller/DivisionController.php:90-93` (`GET /api/seasons/{id}/divisions`) — un `$teamRepository->find()` par équipe, alors que l'entité `Team` est déjà accessible depuis `$teamStat->getTeam()` ;
- `api/src/Controller/TeamController.php:55-58` (`GET /api/teams/{id}?expand=stats`) — pour **chaque** statistique de l'équipe, l'intégralité des `TeamStat` de la division est rechargée afin de calculer une position au classement.

Ce n'est pas une hypothèse de lecture : le nombre de requêtes a été **mesuré** en instrumentant la couche DBAL par un intergiciel de comptage, sur des jeux de données de taille croissante (5 joueurs par équipe) :

| Équipes dans la division | `/divisions/{id}/details` | `/divisions/{id}/teams` | `/seasons/{id}/divisions` |
|---:|---:|---:|---:|
| 4 | 12 | 10 | 6 |
| 8 | 20 | 18 | 10 |
| 16 | 36 | 34 | 18 |
| **24** | **52** | **50** | **26** |

La progression est strictement linéaire : `2N + 4`, `2N + 2` et `N + 2` requêtes respectivement, où *N* est le nombre d'équipes. À l'échelle actuelle de la ligue (24 équipes), **afficher une page de division coûte 52 allers-retours vers PostgreSQL** là où deux suffiraient.

Une cause structurelle sous-jacente mérite d'être notée : l'entité `Team` (`api/src/Entity/Team.php`) ne déclare pas d'association inverse vers `Player` — seul `Player::$team` existe (`api/src/Entity/Player.php:22-23`). L'ORM ne peut donc pas charger les joueurs par jointure, ce qui rend l'aller-retour par équipe presque inévitable dans le code actuel. Par ailleurs, aucun repository n'utilise de jointure de chargement : une seule occurrence de `leftJoin` existe dans tout `src/Repository/` (`GameRepository.php:57`), et elle sert à filtrer, pas à charger.

### 3.2 Solution proposée

Remplacer les boucles par deux requêtes DQL à nombre constant : une requête `TeamStat` avec jointure sur `team` et `captain`, puis une requête `Player … WHERE team IN (:ids)` regroupée en mémoire par équipe.

**Ce prototype a été écrit et exécuté**, sur les mêmes jeux de données que ci-dessus :

| Équipes | Code actuel | Prototype | Réduction |
|---:|---:|---:|---:|
| 4 | 12 | **2** | −83 % |
| 8 | 20 | **2** | −90 % |
| 16 | 36 | **2** | −94 % |
| 24 | 52 | **2** | −96 % |

Le prototype produit la même structure de données (équipes triées par points, joueurs rattachés, capitaine résolu). Le nombre de requêtes devient **indépendant de la taille de la ligue**.

Deux compléments, moins urgents : déclarer l'association inverse `Team::$players` pour permettre les jointures de chargement, et sortir le tri du classement de PHP (`usort`) vers un `ORDER BY` SQL — ce qui, sur une division, ne change rien en performance mais rend l'intention lisible.

### 3.3 Gain attendu

Le **nombre de requêtes** est une mesure directe et transposable : le code ORM emprunté est identique quel que soit le moteur, donc les 52 → 2 valent aussi en production sur PostgreSQL.

La **latence** en revanche n'est pas transposable, et il faut le dire clairement. Les mesures ci-dessus ont été prises sur SQLite en processus, où une requête coûte quelques microsecondes. En production, PostgreSQL tourne dans un conteneur distinct : chaque requête ajoute un aller-retour réseau, typiquement 0,3 à 1 ms sur un réseau Docker local, auquel s'ajoute l'hydratation Doctrine.

Estimation modélisée, à considérer comme un ordre de grandeur :

| | 24 équipes, code actuel | 24 équipes, après R2 |
|---|---|---|
| Requêtes | 52 | 2 |
| Coût d'aller-retour cumulé | ≈ 15 à 50 ms | **≈ 1 à 2 ms** |
| Part du budget « < 300 ms » (SUPERVISION § 4) | 5 à 17 % | < 1 % |

Le gain absolu est donc réel mais **modeste au volume actuel** : il ne faut pas le survendre. Son intérêt véritable est ailleurs :

1. **Il supprime une pente.** Le coût croît linéairement avec la ligue. À 48 équipes, on parle de 100 requêtes par affichage de page.
2. **Il libère le budget de latence** que R3 consommera pour d'autres usages.
3. **Il divise la charge PostgreSQL** aux moments qui comptent — les soirées de match, où le classement est consulté simultanément par plusieurs dizaines de joueurs sur un VPS à 2 Go.

**Recommandation de méthode** : relever la latence réelle des trois endpoints via une sonde Uptime Kuma dédiée **avant** l'optimisation, pour disposer d'un avant/après mesuré et non modélisé. Coût : 15 minutes, inclus dans le chiffrage.

### 3.4 Coûts, risque, attractivité

| | |
|---|---|
| **Coût en jours-homme** | **1,5 à 2,5 j** — 0,5 j par endpoint pour les trois principaux, plus 0,5 j de sondes et de vérification avant/après. Le prototype validé réduit l'incertitude sur cette estimation |
| **Coût financier** | **0 €** |
| **Risque** | **Moyen.** La réécriture touche le format de réponse d'endpoints consommés par le frontend et par le bot. Une différence même mineure (clé absente, ordre du classement) casse l'affichage. **C'est précisément pourquoi R1 doit précéder R2** : `DivisionControllerTest` et `TeamControllerTest` vérifient déjà la structure de ces réponses, mais cette garantie ne vaut que si la suite est exécutée. Réaliser R2 sans R1 serait imprudent |
| **Effet sur l'attractivité** | Direct sur la page la plus consultée du site — le classement de division. Le gain sera peu perceptible aujourd'hui ; il devient perceptible en soirée de match et indispensable si la ligue grandit |

---

## 4. R3 — Mettre en cache les données de classement (HTTP et service worker)

**Priorité : 3.**

### 4.1 Constat, avec preuve

Aucune réponse de l'API n'est mise en cache, à aucun niveau. La recherche des en-têtes de cache dans `api/src/` et `api/config/` ne remonte **qu'une seule occurrence**, et elle va dans le sens inverse : `HealthController.php:68` positionne `Cache-Control: no-store, no-cache, must-revalidate` — ce qui est correct pour une sonde de santé.

Aucun autre endpoint ne renvoie de `Cache-Control`, d'`ETag` ni de `Last-Modified`. Chaque consultation du classement déclenche donc l'intégralité de la chaîne Traefik → Nginx → PHP-FPM → PostgreSQL, y compris lorsque la réponse est rigoureusement identique à celle servie trente secondes plus tôt.

Côté frontend, l'application est déjà une PWA (`SBL-app/vite.config.js`, greffon `vite-plugin-pwa` en stratégie `injectManifest`), mais son service worker (`SBL-app/src/sw.js`) se limite à `precacheAndRoute(self.__WB_MANIFEST)` : il **précache les fichiers statiques et rien d'autre**. Aucune règle de cache d'exécution ne couvre les appels `/api`. Conséquence concrète : l'application est installable sur téléphone, s'ouvre hors connexion — et affiche une page vide, puisque toutes ses données proviennent d'appels réseau non mis en cache.

Le profil d'accès s'y prête pourtant particulièrement bien : le classement d'une division ne change **que lorsqu'un résultat de match est enregistré**, soit quelques fois par semaine, alors qu'il est consulté en continu.

### 4.2 Solution proposée

Trois couches, indépendantes et déployables séparément :

1. **En-têtes HTTP sur les GET publics** (`/divisions`, `/divisions/{id}/details`, `/seasons/{id}/divisions`, `/teams`) : `Cache-Control: public, max-age=60, stale-while-revalidate=300` plus un `ETag` calculé sur le corps de la réponse. Les requêtes conditionnelles répondent alors `304 Not Modified` — quelques centaines d'octets, sans requête SQL.
2. **Cache d'exécution dans le service worker** : règle Workbox `StaleWhileRevalidate` sur les routes `/api/**` en méthode GET, avec expiration à 5 minutes. L'utilisateur voit instantanément la dernière version connue, la mise à jour arrive en arrière-plan, et **l'application devient consultable hors connexion**.
3. **Cache applicatif optionnel** sur les agrégats les plus coûteux, via le pool `cache.app` **déjà configuré** (`api/config/packages/doctrine.yaml`, lignes 42-52 : `doctrine.result_cache_pool` est bien câblé comme cache de résultats en environnement `prod`, mais aucune requête du projet n'appelle `enableResultCache()`, si bien qu'il ne sert jamais), avec invalidation explicite à l'enregistrement d'un résultat de match (`MatchResultController`, `TeamStatCalculatorService`).

Les couches 1 et 2 sont sans effet de bord notable. La couche 3 introduit un état à invalider : à ne mettre en œuvre que si les mesures montrent que les deux premières ne suffisent pas.

### 4.3 Gain attendu

| Effet | Chiffrage | Nature |
|---|---|---|
| Requêtes servies sans PHP ni SQL | **60 à 80 %** des GET publics sur une soirée de match | estimé — dépend du taux de revisite, non instrumenté à ce jour |
| Latence perçue sur une donnée déjà consultée | ≈ 100-200 ms → **< 20 ms** (lecture depuis le cache du service worker) | modélisé |
| Charge PostgreSQL en pic de soirée | réduction du même ordre que le taux de succès du cache | modélisé |
| Consultation du classement hors connexion | **impossible → possible** | fonctionnel |

Le chiffrage du taux de succès est le plus incertain de tout ce document : il dépend d'un comportement utilisateur qui n'est mesuré nulle part aujourd'hui. La fourchette 60-80 % est une hypothèse fondée sur le profil d'usage (consultations répétées d'une même page pendant une soirée), pas sur une observation.

### 4.4 Coûts, risque, attractivité

| | |
|---|---|
| **Coût en jours-homme** | **1 à 2 j** — 0,5 j pour les en-têtes HTTP et l'ETag (un abonné à `kernel.response` suffit), 0,5 j pour la règle Workbox, 1 j supplémentaire si la couche 3 est retenue |
| **Coût financier** | **0 €** — aucun service ajouté : ni Redis, ni Varnish, ni CDN. Le cache HTTP s'appuie sur les navigateurs et le cache applicatif sur le système de fichiers déjà configuré |
| **Risque** | **Moyen, et de nature différente des précédents : le risque est celui de la donnée périmée.** Un capitaine qui saisit un résultat et ne le voit pas apparaître conclura à un bug. Deux garde-fous : un `max-age` court (60 s) accepté comme délai maximal de fraîcheur, et l'exclusion systématique des endpoints authentifiés et des méthodes d'écriture. Risque secondaire, classique sur les PWA : un service worker mal versionné peut servir indéfiniment une donnée obsolète — l'option `registerType: 'autoUpdate'` déjà en place le limite |
| **Effet sur l'attractivité** | **Le plus fort des cinq.** C'est la seule recommandation dont l'effet est immédiatement visible par un joueur : ouverture instantanée du classement, consultation possible dans le métro ou dans une salle mal couverte. La PWA est déjà installable ; cette mesure lui donne enfin l'autonomie qu'un utilisateur attend d'une application installée |

---

## 5. R4 — Établir une barrière de déploiement : pré-production éphémère et retour arrière documenté

**Priorité : 4.**

### 5.1 Constat, avec preuve

La procédure de mise à jour tient en trois commandes (`PROCEDURE_DEPLOIEMENT.md`, § « Mise à jour de l'application ») :

```bash
git pull origin main
sudo docker compose up -d --build
sudo docker compose exec api php bin/console doctrine:migrations:migrate --no-interaction
```

Cette séquence présente trois faiblesses, toutes vérifiables dans la documentation existante :

1. **Les migrations s'exécutent d'abord en production.** Aucun essai préalable n'a lieu sur une copie de la base. Le dispositif de supervision est d'ailleurs explicitement construit autour de ce risque : `docs/SUPERVISION.md` § 3.2 décrit la détection d'un « déploiement où le code est à jour mais où les migrations ont échoué » et fixe l'indicateur « migrations en attente » à une tolérance nulle. **La supervision détecte la panne ; rien ne l'empêche.**
2. **Aucun retour arrière n'est documenté.** Le chapitre « Dépannage » de la procédure propose de consulter les journaux et de redémarrer les conteneurs. Il n'existe aucune marche à suivre pour revenir à la version précédente : ni image Docker étiquetée, ni migration inverse, ni restauration coordonnée du code et de la base. En cas de déploiement défectueux, la seule issue est de corriger en avant, sous pression.
3. **L'écart entre l'environnement de test et la production n'est jamais franchi.** Les tests fonctionnels s'exécutent sur SQLite (`api/phpunit.xml.dist` : `DATABASE_URL="sqlite:///…"`) alors que la production utilise PostgreSQL 16. Différences de typage, de tri, de gestion des séquences : une classe entière de défauts ne peut structurellement pas être détectée avant la production.

### 5.2 Solution proposée

Une pré-production **éphémère et locale au VPS**, plutôt qu'un second serveur — le budget l'impose, et c'est de toute façon suffisant pour ce que l'on cherche à vérifier :

1. **Un profil Compose `staging`** : les mêmes images, une base PostgreSQL distincte, aucune exposition publique (accès par tunnel SSH), démarré à la demande et arrêté juste après.
2. **Restauration d'un vrai jeu de données** : le script `docker/backup/restore.sh` existe déjà, est testé, et sait restaurer un dump dans une base neuve (`docs/SAUVEGARDE.md` § 6). Il fournit gratuitement le socle de la pré-production. C'est la brique la plus coûteuse du dispositif et elle est **déjà écrite**.
3. **Un script de vérification post-déploiement** : appel de `/api/health` (qui contrôle déjà connectivité PostgreSQL, latence, état des migrations et version déployée) suivi de quelques GET sur les endpoints critiques, avec contrôle des codes HTTP et de la présence des clés attendues. Exécuté sur la pré-production, puis à nouveau sur la production juste après bascule.
4. **Une procédure de retour arrière écrite et essayée au moins une fois** : étiquetage des images Docker par version (`APP_VERSION` est déjà injecté au build — `api/Dockerfile`), conservation de l'image N-1, et arbre de décision explicite pour le cas d'une migration déjà appliquée, qui est le seul cas réellement difficile.

Point de vigilance à trancher par la mesure : le VPS dispose de 2 Go de RAM (`PROCEDURE_DEPLOIEMENT.md`, prérequis). Faire coexister temporairement une seconde base PostgreSQL et une seconde instance PHP-FPM est plausible mais **non vérifié**. Si la marge s'avère insuffisante, l'alternative est un second VPS d'entrée de gamme allumé à la demande, ou une exécution sur le poste de développement, ce qui perd la fidélité à l'environnement réel.

### 5.3 Gain attendu

| Effet | Chiffrage | Nature |
|---|---|---|
| Défauts de migration atteignant la production | division par ≈ 2 sur les défauts détectables par un essai de migration | estimé — aucun historique d'incidents de déploiement n'est consigné à ce jour, ce qui interdit un chiffrage sérieux |
| Détection des écarts SQLite / PostgreSQL | **impossible → systématique** | fonctionnel |
| Durée d'un retour arrière | indéterminée (improvisation) → **≈ 10 min** avec une procédure écrite et essayée | estimé |
| Indisponibilité sur incident de déploiement | contribution directe à la cible « ≥ 99 % » (SUPERVISION § 4) | modélisé |
| Surcoût de délai par déploiement | **+ 10 à 15 min** | estimé |

Il faut assumer ce dernier chiffre : cette recommandation **allonge** le délai de mise en œuvre de chaque déploiement. C'est un arbitrage explicite entre vitesse et sûreté, et il ne se justifie que parce que la population servie — une ligue en activité — subit directement toute panne de production.

### 5.4 Coûts, risque, attractivité

| | |
|---|---|
| **Coût en jours-homme** | **2,5 à 4 j** — 1 j pour le profil Compose et la restauration, 0,5 j pour le script de vérification, 1 j pour la procédure de retour arrière et son essai réel, 0,5 à 1,5 j de marge pour les difficultés de mémoire du VPS |
| **Coût financier** | **0 €** dans le scénario « même VPS ». **≈ 5 à 8 € par mois** si un second VPS d'entrée de gamme s'avère nécessaire — à n'engager qu'après avoir constaté que la mémoire disponible ne suffit pas |
| **Risque** | **Faible sur le principe, moyen à l'exécution.** Le risque réel est la consommation mémoire : démarrer une pré-production pendant que la production tourne peut provoquer une éviction OOM du conteneur PostgreSQL de production — c'est-à-dire causer précisément l'incident que le dispositif vise à prévenir. Mitigation obligatoire : plafonds `mem_limit` sur les services de pré-production, et démarrage hors des heures de match |
| **Effet sur l'attractivité** | Indirect. Sa valeur se mesure aux incidents qui n'arrivent pas. C'est aussi la recommandation qui rend possible une **communication honnête avec le staff SBL** : annoncer une évolution testée sur données réelles n'a pas le même poids qu'annoncer une évolution poussée en production et surveillée |

---

## 6. R5 — Externaliser les sauvegardes hors du VPS, chiffrées

**Priorité : 5 en ordonnancement, mais la plus haute en gravité si l'incident survient.**

### 6.1 Constat, avec preuve

Un dispositif de sauvegarde automatisé existe et il est sérieux : `pg_dump` quotidien à 3 h 30, rétention 7 jours + 4 semaines, et surtout **vérification de chaque dump par restauration effective dans une base jetable** — un dump non vérifié n'est jamais compté comme réussi (`docs/SAUVEGARDE.md` § 5, `docker/backup/backup.sh`). La supervision couvre les deux modes de panne : échec de la sauvegarde (webhook Discord) et non-exécution de la sauvegarde (sonde push Uptime Kuma avec période de grâce de 26 h).

Sa limite est documentée sans détour par `docs/SAUVEGARDE.md` § 8 :

> **Les sauvegardes résident sur la machine sauvegardée.** […] le point de défaillance unique est réduit, pas éliminé.

Concrètement : la perte du VPS — défaillance matérielle de l'hébergeur, suppression accidentelle de l'instance, compromission — emporte **simultanément la base de production et l'intégralité de ses sauvegardes**. Le dispositif protège de la corruption logique et de l'erreur humaine, qui sont les incidents les plus fréquents, mais pas du seul incident qui soit définitif.

Cette recommandation a en outre une particularité méthodologique intéressante pour le dossier : elle a **déjà été anticipée par une décision de conception**. Le montage hôte (`BACKUP_HOST_PATH`) a été préféré à un volume Docker nommé « précisément […] pour que cette recopie soit triviale à ajouter, sans modifier l'application ». Le travail préparatoire est fait ; il reste à en tirer parti.

### 6.2 Solution proposée

1. **Chiffrement des dumps avant sortie du VPS** avec `age` (une clé publique sur le VPS, la clé privée conservée hors ligne). Cette étape est **obligatoire, pas optionnelle** : les dumps contiennent des identifiants Discord et des adresses de courriel, donc des données à caractère personnel. Les déposer en clair chez un tiers créerait un problème de conformité là où il n'y en avait pas.
2. **Synchronisation vers un stockage objet** par `rclone sync`, planifiée sur l'hôte après l'horaire de sauvegarde, avec une rétention distante de 30 jours — la commande exacte est déjà esquissée dans `docs/SAUVEGARDE.md` § 8.
3. **Supervision de la copie distante** sur le modèle déjà retenu pour la sauvegarde locale : une sonde push Uptime Kuma dédiée, période de grâce de 26 h, alimentée par la réussite de `rclone`. Le principe établi en § 7 de `SAUVEGARDE.md` s'applique tel quel — c'est l'**absence** de signal qui doit alerter.
4. **Un essai de restauration depuis la copie distante**, documenté, incluant le déchiffrement. Une sauvegarde distante jamais restaurée n'est pas une sauvegarde.

### 6.3 Gain attendu

| Effet | Chiffrage | Nature |
|---|---|---|
| Scénarios de perte définitive de données | perte du VPS = **perte totale** → **perte nulle**, RPO conservé à 24 h | fonctionnel |
| Point de défaillance unique | « réduit » (formulation de `SAUVEGARDE.md` § 8) → **éliminé** pour la donnée | fonctionnel |
| Conformité au traitement des données personnelles | dumps en clair sur une seule machine → **chiffrés au repos et hors site** | fonctionnel |
| RTO en cas de perte du VPS | indéterminé → **≈ 2 à 4 h** (reconstruction du VPS + restauration) | estimé |

Le RPO reste de 24 heures : un incident survenant à 22 h fait perdre la soirée de match en cours. Descendre sous ce seuil exigerait l'archivage WAL continu, écarté en § 7 pour des raisons de proportionnalité.

### 6.4 Coûts, risque, attractivité

| | |
|---|---|
| **Coût en jours-homme** | **0,5 à 1 j** — la brique locale existe et est testée ; il ne reste que le chiffrement, la synchronisation, la sonde et l'essai de restauration |
| **Coût financier** | **≈ 0,50 à 2 € par mois.** Le volume est faible (quelques dizaines de Mio par dump, soit bien moins de 10 Go avec 30 jours de rétention) et les offres de stockage objet compatibles S3 se situent autour de 5 à 7 € par To et par mois. C'est la seule dépense récurrente de tout le document |
| **Risque** | **Faible sur le dispositif, réel sur la gestion des clés.** Le danger n'est pas la sauvegarde mais la clé de déchiffrement : une clé perdue rend les archives distantes inutilisables, et une clé stockée sur le VPS annule l'intérêt du chiffrement. La clé privée doit être conservée hors du VPS, sur un support distinct, avec une copie de secours — et cette exigence doit figurer dans la procédure |
| **Effet sur l'attractivité** | Indirect, mais c'est l'argument de confiance le plus fort vis-à-vis du staff SBL. Une ligue confie à cette application l'historique de ses saisons ; pouvoir affirmer que cet historique survivrait à la disparition du serveur est un engagement concret, pas une promesse |

---

## 7. Synthèse et trajectoire

### 7.1 Tableau récapitulatif

| # | Recommandation | Gain principal | Jours-homme | Coût financier | Risque | Priorité |
|---|---|---|---:|---|---|---:|
| **R1** | Tests en intégration continue + correction des 13 échecs | 0 % → ~100 % des régressions couvertes détectées avant production ; 1 défaut de production révélé | 1,5 – 2,5 | 0 € | Faible | **1** |
| **R2** | Suppression des N+1 sur le classement | 52 → 2 requêtes à 24 équipes (−96 %), mesuré sur prototype | 1,5 – 2,5 | 0 € | Moyen | **2** |
| **R3** | Cache HTTP + service worker | 60-80 % des GET servis sans SQL ; consultation hors connexion | 1 – 2 | 0 € | Moyen | **3** |
| **R4** | Pré-production éphémère + retour arrière | Défauts de migration interceptés ; retour arrière ≈ 10 min | 2,5 – 4 | 0 € (ou 5-8 €/mois) | Faible / Moyen | **4** |
| **R5** | Sauvegardes externalisées et chiffrées | Élimination du point de défaillance unique sur la donnée | 0,5 – 1 | 0,50 – 2 €/mois | Faible | **5** |
| | **Total** | | **7 – 12 j** | **≈ 1 à 10 €/mois** | | |

À titre de comparaison indicative uniquement, ces 7 à 12 jours représenteraient de l'ordre de 2 800 à 4 800 € HT s'ils étaient sous-traités. Sur ce projet, le coût réel décaissé est celui de la colonne « coût financier » : **environ 1 à 10 € par mois**, dont la quasi-totalité tient au stockage distant de R5 et à l'éventuel second VPS de R4.

### 7.2 Ordonnancement recommandé

L'ordre n'est pas seulement une hiérarchie de valeur : il traduit des dépendances techniques réelles.

```
R1 (tests en CI) ──────► R2 (N+1) ──────► R3 (cache)
     │                      │
     │                      └─ R2 modifie le format de réponse d'endpoints
     │                         consommés par le frontend et le bot : sans la
     │                         suite exécutée automatiquement, la régression
     │                         n'est détectée qu'en production.
     │
     └─ R3 masquerait les gains de R2 derrière le cache : optimiser d'abord,
        mettre en cache ensuite, sous peine de mettre en cache un défaut.

R5 (sauvegarde hors site) ─ indépendante, 0,5 j, à intercaler dès qu'un
                            créneau court se présente.

R4 (pré-production) ─ la plus coûteuse, à engager une fois les précédentes
                      stabilisées ; elle sécurise tout ce qui viendra après.
```

**Séquence proposée sur trois mois**, à raison de quelques heures par semaine, ce qui correspond au rythme soutenable d'un projet mené seul :

| Période | Action | Charge |
|---|---|---|
| Semaines 1-2 | R1 — workflow, protection de branche, correction des 13 échecs | 2 j |
| Semaine 3 | R5 — externalisation chiffrée des sauvegardes | 0,5 j |
| Semaines 4-5 | R2 — sondes de référence, puis suppression des N+1 | 2 j |
| Semaines 6-7 | R3 — en-têtes HTTP, ETag, cache d'exécution du service worker | 1,5 j |
| Semaines 8-11 | R4 — pré-production, script de vérification, procédure de retour arrière | 3,5 j |
| Semaine 12 | Relevé des indicateurs et comparaison avant/après | 0,5 j |

### 7.3 Vérification de l'effet obtenu

Une recommandation dont l'effet n'est pas vérifié reste une opinion. Chaque mesure doit être contrôlée sur les indicateurs de `docs/SUPERVISION.md` § 4, complétés par ceux proposés en § 1.2 :

| Recommandation | Comment vérifier | Quand |
|---|---|---|
| R1 | Taux de couverture publié par la CI ; nombre de PR bloquées par un test en échec | à chaque commit |
| R2 | Sonde Uptime Kuma sur `/divisions/{id}/details`, comparaison avant/après | J+1 |
| R3 | Taux de réponses `304` dans les journaux Nginx ; temps de chargement perçu | J+7 |
| R4 | Nombre de défauts interceptés en pré-production ; durée réelle d'un retour arrière essayé | à chaque déploiement |
| R5 | Sonde push dédiée ; essai de restauration depuis la copie distante | mensuel |

---

## 8. Incertitudes d'estimation

Ce chapitre existe parce que plusieurs chiffres de ce document sont fragiles, et qu'il serait malhonnête de les présenter avec la même assurance que les mesures.

**Ce qui est mesuré et solide :**

- Les **nombres de requêtes SQL** (§ 3.1 et 3.2). Ils proviennent d'une instrumentation directe de la couche DBAL sur quatre tailles de jeu de données, et le prototype à 2 requêtes a été exécuté. Ces chiffres sont transposables à PostgreSQL, car le chemin de code ORM est identique.
- Les **345 tests, les 13 échecs, les 4 min 55 s** de durée de suite (§ 2.1). Exécution réelle, reproductible par `php bin/phpunit`.
- L'**absence de cache et l'absence de workflow de tests** (§ 2.1 et 4.1). Constats binaires vérifiables par lecture des fichiers cités.

**Ce qui est modélisé, donc discutable :**

- Les **latences en millisecondes** de § 3.3. Elles reposent sur une hypothèse d'aller-retour PostgreSQL de 0,3 à 1 ms sur réseau Docker, non mesurée sur ce VPS. La fourchette « 15 à 50 ms » peut être fausse d'un facteur 2 à 3 dans les deux sens. Seule une sonde en production permettra de trancher — d'où la recommandation de mesurer avant d'optimiser.
- Le **gain de charge PostgreSQL** de § 4.3, qui découle du taux de succès du cache, lui-même estimé.

**Ce qui est estimé sans base solide, et doit être lu comme tel :**

- Le **taux de succès du cache (60-80 %)** de § 4.3. Aucune donnée de fréquentation n'est collectée à ce jour : ni analytique, ni journalisation exploitée des accès. Cette fourchette repose sur une intuition d'usage, pas sur une observation. Elle devrait être remplacée par une mesure avant que R3 ne soit engagée.
- Le **nombre de défauts de déploiement évités** par R4 (§ 5.3). Il n'existe aucun historique consigné d'incidents de déploiement — le processus de consignation des anomalies (`docs/PROCESSUS_ANOMALIES.md`) est récent. Toute division par deux annoncée serait ici une figure de style. La justification de R4 n'est donc pas statistique mais structurelle : elle repose sur l'existence avérée d'un mode de panne non couvert, pas sur une fréquence observée.
- Les **jours-homme**. Ils supposent un développeur qui connaît le code, sans interruption, et sans découverte de difficulté imprévue. L'expérience du projet montre que R1 en particulier peut déborder : corriger 13 échecs signifie corriger 13 problèmes dont on ne connaît pas encore la nature exacte. La fourchette haute est plus probable que la basse.
- Le **coût du stockage objet** (§ 6.4). Il dépend d'une offre non encore choisie et de la croissance de la base, laquelle est modeste mais non nulle.

**Une limite de méthode, enfin.** Les indicateurs de `docs/SUPERVISION.md` § 4 constituent la base de mesure de ce document, mais le dispositif de supervision est **récent** : il ne dispose pas encore d'un historique suffisant pour établir une ligne de base fiable de disponibilité mensuelle ou de temps de réponse. Les cibles y sont donc, à ce stade, des objectifs de conception et non des moyennes constatées. La première action de valeur — de coût quasi nul — est d'attendre un mois complet de collecte avant de comparer quoi que ce soit à un « avant ».

---

## 9. Ce qui a été délibérément écarté

Les propositions suivantes amélioreraient objectivement le logiciel. Elles sont écartées parce qu'elles ne sont **pas réalisables** dans le cadre du projet, et il est plus utile de dire pourquoi que de les passer sous silence.

| Piste écartée | Motif |
|---|---|
| **Redis pour le cache applicatif** | Un conteneur supplémentaire et 30 à 50 Mo de RAM sur un VPS de 2 Go, pour un volume de données que le cache système de Symfony absorbe sans difficulté. Le pool `cache.app` déjà configuré suffit. Disproportionné. |
| **Prometheus + Grafana** | Écarté pour les mêmes raisons qu'en § 2 de `docs/SUPERVISION.md` : trois conteneurs pour un besoin qu'Uptime Kuma couvre en 100 Mo. |
| **Réplication PostgreSQL / haute disponibilité** | Suppose au minimum un second serveur, donc un doublement du coût d'hébergement, pour une cible de disponibilité (99 %) qui n'en a pas besoin. Une ligue amateur tolère sept heures d'indisponibilité par mois ; elle ne tolère pas une perte de données — c'est pourquoi l'effort porte sur R5 plutôt qu'ici. |
| **Archivage WAL continu (PITR)** | Ramènerait le RPO de 24 h à la seconde, au prix d'un stockage d'archives permanent et d'une procédure de restauration nettement plus complexe (`docs/SAUVEGARDE.md` § 8). Sur des données ressaisissables et à ce volume, le rapport coût/bénéfice n'y est pas. |
| **Migration vers Kubernetes** | Aucun problème actuel du projet n'est un problème d'orchestration. Le coût d'apprentissage et d'exploitation serait supporté seul, pour zéro gain fonctionnel. |
| **Réécriture du frontend / adoption de TypeScript** | La dette de typage du frontend est réelle (aucun test, aucune vérification de types dans `SBL-app/`). Mais c'est un chantier de plusieurs semaines dont le gain porte sur la maintenabilité future, pas sur un problème constaté. À reconsidérer une fois R1 à R5 en place — le pendant frontend de R1 (quelques tests de composants et un `npm run lint` en CI) serait alors le point d'entrée naturel. |

---

## Annexe A — Reproduire la mesure des requêtes N+1

Les chiffres du § 3.1 ont été obtenus par un intergiciel DBAL de comptage, enregistré uniquement dans l'environnement de test, encadrant des appels HTTP réels au noyau Symfony. La méthode est reproductible en une trentaine de lignes :

1. Écrire une classe implémentant `Doctrine\DBAL\Driver\Middleware` qui incrémente un compteur statique dans `prepare()`, `query()` et `exec()`.
2. L'enregistrer sous `when@test` avec l'étiquette de service `doctrine.middleware`.
3. Dans un test étendant `ApiTestCase`, créer une division avec *N* équipes et 5 joueurs par équipe, remettre le compteur à zéro, appeler l'endpoint via `$this->client->request()`, puis relever le compteur.
4. Répéter pour *N* ∈ {4, 8, 16, 24} au moyen d'un `#[DataProvider]`.

Le comptage a été retiré du dépôt après mesure : il s'agissait d'un instrument d'analyse, pas d'un test de non-régression. **Une fois R2 mise en œuvre, il vaudrait la peine de le réintroduire sous forme de test permanent** — un test qui échoue si `/divisions/{id}/details` dépasse un plafond de requêtes est la seule protection durable contre la réapparition d'un N+1, que la relecture de code ne détecte pas de manière fiable.

---

## Références

| Document | Ce qu'il apporte à ces recommandations |
|---|---|
| `docs/SUPERVISION.md` § 4 | Indicateurs et seuils servant de base de mesure |
| `docs/SAUVEGARDE.md` § 8 | Limites connues du dispositif de sauvegarde, à l'origine de R5 |
| `docs/PROCESSUS_ANOMALIES.md` | Circuit de consignation par lequel transiteront les défauts révélés par R1 |
| `docs/JOURNAL_VERSIONS.md` | Cadre de publication des évolutions issues de ces recommandations |
| `PROCEDURE_DEPLOIEMENT.md` | Procédure de déploiement actuelle, dont R4 comble les manques |
| `docs/BLOC4_MISE_EN_ROUTE.md` | Correspondance avec la grille d'évaluation du bloc 4 |
