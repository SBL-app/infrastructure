# Anomalie — Pourcentage d'avancement de saison erroné

> Référence : compétence **C4.2.2** — *Créer et déployer un correctif en respectant le
> processus d'intégration et de déploiement continu, afin de résoudre l'anomalie
> détectée.*
>
> Processus de référence : [`../PROCESSUS_ANOMALIES.md`](../PROCESSUS_ANOMALIES.md) ·
> Template de consignation : `api/.github/ISSUE_TEMPLATE/bug_report.yml`

## Avertissement méthodologique

Ce dossier documente une anomalie **réelle** du projet, survenue en octobre 2024.
Tous les éléments techniques (extraits de code, diffs, dates, empreintes de commit,
volumétries) proviennent de l'historique Git du dépôt `SBL-app/api` et du dump de
production `mysql-baguette-league_alwaysdata_net.sql`.

À la date des faits, le dispositif de collecte et de consignation décrit dans
`PROCESSUS_ANOMALIES.md` **n'existait pas encore** : ni issue GitHub, ni alerte
Monolog, ni Sentry, ni supervision Uptime Kuma. La fiche de consignation de la
section 1 est donc **reconstituée a posteriori**. Chaque champ dont la valeur n'est
pas déductible de l'historique est explicitement signalé comme tel plutôt que
comblé par une hypothèse. La section 4 distingue rigoureusement ce qui s'est
réellement passé en 2024 de la façon dont la même anomalie serait traitée dans la
chaîne actuelle.

## Identification

| Élément | Valeur |
|---|---|
| Dépôt | `github.com/SBL-app/api` |
| Composant | API — `src/Controller/SeasonController.php` |
| Commit d'introduction (défaut A) | `c888109` — 29/09/2024 — *update(seasonController) : add getFinishedMatchPourcent* |
| Propagation par copier-coller | `4617869` — 18/10/2024 — *add match pourcentage to getAllSeason* |
| Commit de correction (défaut A) | `9fda6bd` — 23/10/2024 — *fix(seasonController) : issue with the totalGames in pourcentage math* |
| Commit de correction (défaut B) | `02b93b0` — 11/03/2025 — *fix poucentage count* |
| Auteur | galexand |
| Sévérité retenue | S3 — Mineure |

---

# 1. Fiche de consignation

Les champs ci-dessous reprennent **dans l'ordre et sous le libellé exact** ceux du
template `api/.github/ISSUE_TEMPLATE/bug_report.yml`.

> **Titre de l'issue** : `[BUG] Pourcentage d'avancement des saisons divisé par le nombre de matchs de la division`
> **Labels** : `type:bug`, `severite:s3`, `composant:api`, `statut:confirme`

### Source de la détection *

**Constatée en développement.**

*Justification du choix* — c'est la seule valeur compatible avec l'historique. Les
trois canaux de collecte décrits dans `PROCESSUS_ANOMALIES.md` sont tous
postérieurs : le handler Discord Monolog, Sentry et les sondes Uptime Kuma ont été
mis en place en 2026. Aucune issue GitHub ne référence cette anomalie. Le seul
artefact disponible est le message de commit, qui indique une correction délibérée
d'un calcul (*« issue with the totalGames in pourcentage math »*), sans mention de
signalement externe.

*Point notable* — même si la collecte automatique avait existé, elle **n'aurait pas
détecté cette anomalie** : le code ne lève aucune exception et ne produit aucune
erreur 5xx. La réponse HTTP est un `200 OK` structurellement valide contenant une
valeur fausse. C'est exactement l'angle mort décrit au §1 du processus
(« ce qui échoue en silence »).

### Sévérité *

**S3 — Mineure.** *Fonctionnalité secondaire dégradée, contournement simple.*

*Justification* — l'indicateur d'avancement est un élément d'information, non un
élément de gestion : aucune saisie de résultat, aucune inscription et aucun
calcul de classement n'en dépend. Le staff SBL dispose d'un contournement immédiat
(la page de division affiche les matchs et leurs statuts un par un). En revanche
la donnée est fausse pour **100 % des visiteurs**, ce qui interdit de la
classer S4 : il ne s'agit pas d'un défaut d'affichage mais d'une valeur métier
erronée.

Conformément au processus, la sévérité est fixée par l'impact utilisateur et non
par la difficulté technique : la correction tient en un caractère, l'anomalie
reste S3.

### Composant concerné *

**API (Symfony).**

Deux points d'entrée sont touchés par le même défaut :

- `GET /seasons` — `SeasonController::getAllSeason()`
- `GET /season/{id}/pourcent` — `SeasonController::getFinishedMatchPourcent()`

Le frontend Vue est consommateur mais n'est pas fautif : il affiche fidèlement la
valeur reçue.

### Version applicative *

**Aucun tag applicable — identification par empreinte de commit.**

Le premier tag du dépôt est `v1.0.0` (`a72518e`, 26/06/2025), soit **huit mois après**
les faits. Ni le journal de versions, ni l'endpoint `/api/health` — tous deux
introduits en 2026 — n'existaient. L'identification s'appuie donc sur les commits :

| Rôle | Commit | Date |
|---|---|---|
| Version fautive (`/season/{id}/pourcent`) | `c888109` | 29/09/2024 |
| Version fautive (`/seasons`) | `4617869` | 18/10/2024 |
| Version corrigée | `9fda6bd` | 23/10/2024 |

*Ce champ est précisément celui que le dispositif actuel rend renseignable* : c'est
l'exposition de `version` et `commit` par `/api/health` qui permet aujourd'hui de
relier une anomalie à une entrée du `CHANGELOG.md`.

### Environnement *

**Production.**

Le frontend consommait déjà le champ `percentage` : le commit `59be63f` de
`SBL-app` (18/10/2024) branche l'affichage le jour même de l'introduction du défaut
dans `getAllSeason`.

### Contexte d'apparition *

Le calcul du taux d'avancement a été ajouté le 29/09/2024 (`c888109`) sur une route
dédiée `GET /season/{id}/pourcent`, explicitement annotée dans le code :

```php
//TODO: need to be tested
#[Route('/season/{id}/pourcent', name: 'app_season_pourcent', methods: ['GET'])]
```

Le 18/10/2024 (`4617869`), ce bloc de calcul a été **copié-collé** dans
`getAllSeason()` afin d'enrichir la liste des saisons, sans avoir été testé
entre-temps. Le défaut s'est ainsi retrouvé en deux exemplaires, sur deux routes,
dont une exposée sur la page d'accueil.

L'anomalie n'est pas apparue à la suite d'un déploiement d'infrastructure : elle
est arrivée avec la fonctionnalité elle-même. Elle a donc été **fausse dès le
premier jour** — il n'a jamais existé de version de référence affichant une valeur
correcte, ce qui a retardé sa détection : aucun écart avant/après n'était
observable.

### Étapes de reproduction *

Sur un jeu de données comportant au moins une division de plus d'un match
(données de référence : dump `mysql-baguette-league_alwaysdata_net.sql`, saison I —
4 divisions de 12, 12, 15 et 10 matchs, tous joués) :

1. Se placer sur le commit `4617869` (ou tout commit antérieur à `9fda6bd`).
2. Appeler `GET /seasons` (ou `GET /season/1/pourcent`).
3. Relever le champ `total_games` de la réponse.
4. Comparer à la volumétrie réelle : `SELECT COUNT(*) FROM game g JOIN division d ON g.division_id = d.id WHERE d.season_id = 1;` → **49**.
5. Constater que `total_games` vaut **613** et que `percentage` est divisé d'autant.

Formulation généralisée, indépendante du jeu de données : pour une saison dont les
divisions comportent respectivement `n₁, n₂, … n_d` matchs, l'API renvoie
`total_games = Σ n_d²` au lieu de `Σ n_d`. Le défaut est donc **invisible sur une
division d'un seul match** (`1² = 1`), ce qui explique qu'il ait pu passer une
vérification manuelle rapide sur un jeu de données minimal.

### Comportement attendu *

`GET /seasons` doit retourner, pour chaque saison, le nombre total de matchs
programmés, le nombre de matchs joués et leur rapport en pourcentage.

Sur la saison I du dump : `total_games = 49`, `finished_games = 49`,
`percentage = 100`.

### Comportement constaté *

`total_games` est égal à la somme des carrés du nombre de matchs par division, ce
qui écrase le pourcentage.

| Saison | Matchs par division | `total_games` attendu | `total_games` constaté | `percentage` attendu | `percentage` constaté |
|---|---|---|---|---|---|
| Saison I | 12, 12, 15, 10 | 49 | **613** | 100 % | **7,99 %** |
| Saison II | 12, 15, 15, 15, 15, 15 | 87 | **1269** | 100 % | **6,86 %** |

*Valeurs calculées à partir des tables `game` et `division` du dump
`mysql-baguette-league_alwaysdata_net.sql`.*

**Précision importante sur ce qui était réellement affiché.** Un second défaut,
indépendant, se superpose au premier (voir section 2.4) : le libellé de statut
recherché, `'match fini'`, ne correspond à aucune ligne de la table `game_status`
(valeurs réelles : `à joué`, `joué`, `en cours`, `reporté`). `finished_games`
valait donc **0** et la valeur effectivement affichée en production était **0 %**.
Les 7,99 % du tableau ci-dessus isolent l'effet du seul défaut arithmétique — c'est
la valeur qu'aurait produite le code une fois le défaut de statut corrigé.

### Lien Sentry

**Sans objet.** Sentry (`sentry/sentry-symfony`) a été intégré au projet en 2026.
Champ non obligatoire au template.

### Journaux et messages d'erreur

**Aucun.**

C'est la caractéristique déterminante de cette anomalie : elle ne produit ni
exception, ni erreur PHP, ni code HTTP d'erreur. La requête aboutit en `200 OK`
avec un corps JSON conforme au schéma attendu.

```
GET /seasons  →  200 OK
[{"id":1,"name":"Saison I","start_date":"21-03-2022","end_date":"02-05-2022",
  "total_games":613,"finished_games":0,"percentage":0}]
```

Aucun dispositif de journalisation, quel que soit son niveau de finesse, ne peut
signaler cette réponse : elle est syntaxiquement irréprochable. Seuls un test
portant sur la valeur métier ou une lecture humaine de l'affichage pouvaient la
révéler. Ce constat justifie directement l'exigence formulée en section 5 : le
correctif d'une anomalie silencieuse **doit** être accompagné d'un test de
non-régression, faute de quoi aucun canal de collecte ne détectera sa récidive.

### Impact utilisateurs *

- **Périmètre** : tous les visiteurs du site, sans authentification requise. La
  page des saisons et le composant d'accueil sont publics.
- **Surfaces touchées** : barre de progression et badge d'état
  (`SBL-app/src/views/SeasonsView.vue`, `src/components/TheSeasons.vue`,
  `src/components/IncomingEvents.vue`). Le badge bascule sur « terminé » lorsque
  `percentage === 100` : ce seuil étant inatteignable, **toutes les saisons
  restaient affichées « en cours », y compris celles achevées depuis 2022**.
- **Données concernées** : les deux saisons présentes en base, soit 136 matchs.
- **Contournement** : consulter la page de division, qui liste les matchs et leurs
  statuts individuellement. Contournement simple mais fastidieux, et indisponible
  pour un visiteur cherchant une vue d'ensemble.
- **Urgence réelle** : faible. Aucune opération de gestion n'est bloquée. Le
  préjudice est un défaut de crédibilité de l'information publiée.

### Analyse préliminaire et piste de correction

Cause suspectée : dans la boucle sur les matchs d'une division,
`$totalGames += count($games)` ajoute le cardinal complet de la division à chaque
itération, alors que la boucle itère déjà une fois par match.

Piste : remplacer par une incrémentation unitaire `$totalGames++`, aligner les deux
occurrences (`getAllSeason` et `getFinishedMatchPourcent`), puis **factoriser le
calcul dans une méthode unique** pour supprimer la duplication qui a permis la
propagation du défaut.

Vérifier également le libellé `'match fini'` recherché dans `game_status` : il ne
semble correspondre à aucune valeur en base.

---

# 2. Analyse de la cause racine

## 2.1 Le code fautif

`src/Controller/SeasonController.php`, tel qu'introduit par `c888109` puis dupliqué
par `4617869` :

```php
$totalGames = 0;
$finishedGames = 0;
$finishedStatus = $gameStatusRepository->findOneBy(['name' => 'match fini']);
$divisions = $divisionRepository->findBy(['season' => $season]);

foreach ($divisions as $division) {
    $games = $gameRepository->findBy(['division' => $division]);
    foreach ($games as $game) {
        $totalGames += count($games);          // ← défaut A
        if ($game->getStatus() === $finishedStatus) {
            $finishedGames++;                  // ← incrémentation correcte
        }
    }
}

$percentage = $totalGames > 0 ? ($finishedGames / $totalGames) * 100 : 0;
```

## 2.2 Mécanisme du défaut A

`count($games)` est une **expression invariante dans la boucle interne** : elle vaut
`n_d`, le nombre de matchs de la division courante, à chaque itération. Or la
boucle s'exécute déjà exactement `n_d` fois.

```
Pour une division de n matchs :
    contribution attendue  =  n
    contribution obtenue   =  n × n  =  n²

Pour une saison de d divisions :
    total attendu  =  Σ n_d
    total obtenu   =  Σ n_d²
```

Le numérateur `finishedGames` étant, lui, incrémenté unitairement, le pourcentage
renvoyé vaut :

```
        Σ joués                              Σ joués
   ─────────────────  × 100     au lieu de  ─────────  × 100
       Σ n_d²                                 Σ n_d
```

Sur une saison à division unique de `n` matchs, cela revient exactement à
**diviser le pourcentage réel par `n`**.

**Pourquoi le défaut a échappé à la vérification manuelle** : pour `n_d = 1`, alors
`n² = n`. Un jeu de données de test comportant une division d'un seul match produit
un résultat rigoureusement correct. L'anomalie n'apparaît qu'à partir de deux
matchs par division et son amplitude croît linéairement avec la volumétrie — donc
au fil de la saison, à mesure que le résultat devient visible.

## 2.3 Vérification sur les données réelles

Extraction depuis les tables `division` et `game` du dump
`mysql-baguette-league_alwaysdata_net.sql` (136 matchs au total) :

| Saison | Divisions | Matchs par division | `Σ n_d` (attendu) | `Σ n_d²` (obtenu) | Facteur d'erreur |
|---|---|---|---|---|---|
| Saison I | 4 | 12, 12, 15, 10 | 49 | 613 | ×12,5 |
| Saison II | 6 | 12, 15, 15, 15, 15, 15 | 87 | 1269 | ×14,6 |

Le facteur d'erreur est la moyenne des `n_d` pondérée par `n_d` — il augmente donc
avec la taille des divisions. Sur une ligue plus fournie, l'écart se creuse.

## 2.4 Le défaut B, indépendant et non traité par le correctif

```php
$finishedStatus = $gameStatusRepository->findOneBy(['name' => 'match fini']);
```

Les statuts effectivement présents en base sont :

```sql
INSERT INTO `game_status` (`id`, `name`) VALUES
(1, 'à joué'), (2, 'joué'), (3, 'en cours'), (4, 'reporté');
```

`'match fini'` ne correspond à aucun d'eux. `findOneBy` retourne donc `null`, et la
comparaison stricte `$game->getStatus() === $finishedStatus` est **toujours fausse**
— une entité `GameStatus` n'est jamais identique à `null`. `finishedGames` reste
figé à `0`, quel que soit l'état réel des matchs.

Ce diagnostic est corroboré de façon indépendante par l'historique : le commit
`02b93b0` du 11/03/2025 remplace `'match fini'` par `'joué'` dans les deux méthodes,
avec pour seul message « fix poucentage count ». Le défaut B a donc survécu
**5 mois et 12 jours** au correctif du défaut A.

Conséquence sur la chronologie de l'affichage :

| Période | Défaut A | Défaut B | Valeur affichée (saison achevée) |
|---|---|---|---|
| 29/09/2024 → 23/10/2024 | actif | actif | 0 % |
| 23/10/2024 → 11/03/2025 | corrigé | actif | 0 % |
| à partir du 11/03/2025 | corrigé | corrigé | 100 % |

Le correctif `9fda6bd` était **juste mais sans effet observable** : l'utilisateur a
vu 0 % avant comme après. C'est le meilleur argument possible en faveur de la
vérification post-correction exigée en section 5 — sans critère de recette explicite
sur la valeur métier, un correctif exact peut être livré et clos sans que le
symptôme disparaisse.

## 2.5 Cause racine organisationnelle

Le défaut de code n'est que le symptôme. Quatre facteurs, tous vérifiables dans
l'historique, expliquent son introduction puis sa persistance :

| Facteur | Preuve dans l'historique |
|---|---|
| **Absence de test** | Le premier commit touchant `tests/` date du 20/06/2025 (`8ebb84c`), soit 8 mois après. Le code portait lui-même la mention `//TODO: need to be tested`. |
| **Duplication du code** | Le bloc de calcul est copié-collé de `getFinishedMatchPourcent` vers `getAllSeason` (`4617869`), doublant la surface du défaut sans revue. |
| **Absence de revue** | Le commit est poussé directement sur la branche de travail, sans pull request ni relecture par un tiers. |
| **Absence de CI** | Le premier workflow GitHub Actions du dépôt date du 15/03/2026 (`cda1524`). Aucun contrôle automatique n'existait. |

Le `//TODO: need to be tested` est ici l'élément le plus significatif : l'auteur
avait **identifié le risque** au moment d'écrire le code. Ce qui a manqué n'est pas
la conscience du besoin de test, mais un mécanisme rendant impossible la fusion
d'un code non couvert. C'est précisément la fonction d'une chaîne d'intégration
continue, et c'est l'objet de la section 4.

---

# 3. Correctif appliqué

## 3.1 Commit

```
commit 9fda6bdb0d2a27f2481dd0d4ec6e9885c8da0c2c
Author:     galexand <giordana.alex@gmail.com>
AuthorDate: Wed Oct 23 15:55:49 2024 +0200

    fix(seasonController) : issue with the totalGames in pourcentage math

 src/Controller/SeasonController.php | 45 +++++++++++++++++++++----------------
 1 file changed, 26 insertions(+), 19 deletions(-)
```

## 3.2 Diff commenté

### Hunk 1 — `getAllSeason()` : le correctif proprement dit

```diff
@@ -24,17 +24,17 @@ class SeasonController extends AbstractController
         foreach ($divisions as $division) {
             $games = $gameRepository->findBy(['division' => $division]);
             foreach ($games as $game) {
-                    $totalGames += count($games);
+                    $totalGames ++;
                 if ($game->getStatus() === $finishedStatus) {
                     $finishedGames++;
                 }
             }
         }
         $percentage = $totalGames > 0 ? ($finishedGames / $totalGames) * 100 : 0;
```

**Commentaire.** Correction minimale et exacte : le compteur est incrémenté une
fois par itération, ce qui aligne son sémantisme sur celui de `$finishedGames` juste
en dessous. C'est la bonne granularité de correctif — une ligne, un défaut, aucun
effet de bord. Le garde `$totalGames > 0` protégeant la division était déjà présent
et reste pertinent.

### Hunk 2 — `getFinishedMatchPourcent()` : la seconde occurrence

```diff
@@ -111,34 +119,33 @@ class SeasonController extends AbstractController
     public function getFinishedMatchPourcent(Season $season, ...): JsonResponse
     {
-        $totalGames = 0;
-        $finishedGames = 0;
-        $finishedStatus = $gameStatusRepository->findOneBy(['name' => 'match fini']);
+        $nbTotalGames = 0;
+        $nbFinishedGames = 0;
         $divisions = $divisionRepository->findBy(['season' => $season]);
         foreach ($divisions as $division) {
             $games = $gameRepository->findBy(['division' => $division]);
             foreach ($games as $game) {
-                $totalGames += count($games);
-                if ($game->getStatus() === $finishedStatus) {
-                    $finishedGames++;
-                }
+                $nbTotalGames ++;
+                if ($game->getStatus() === $gameStatusRepository->findOneBy(['name' => 'match fini'])) {
+                    $nbFinishedGames++;
+                }
             }
         }
-        $percentage = $totalGames > 0 ? ($finishedGames / $totalGames) * 100 : 0;
+        $pourcent = $nbTotalGames > 0 ? ($nbFinishedGames / $nbTotalGames) * 100 : 0;
         return $this->json([
-            'total_games' => $totalGames,
-            'finished_games' => $finishedGames,
-            'percentage' => $percentage
+            'total' => $nbTotalGames,
+            'finished' => $nbFinishedGames,
+            'pourcent' => $pourcent
         ]);
     }
```

**Commentaire.** Le défaut est bien corrigé sur la seconde occurrence, mais le
correctif y **excède son périmètre** et introduit trois régressions :

1. **Régression de performance (N+1).** `findOneBy(['name' => 'match fini'])` était
   hissé hors des boucles ; il est ici replacé **dans la condition, au cœur de la
   boucle interne**. Une requête `SELECT` est désormais émise par match évalué. Sur
   la saison II du dump, cela transforme 1 requête en 87. Le cache d'identité de
   Doctrine amortit le coût mais ne supprime pas l'aller-retour vers la couche ORM.

2. **Rupture du contrat d'API.** Les clés de la réponse sont renommées
   `total_games → total`, `finished_games → finished`, `percentage → pourcent`.
   Le renommage n'est mentionné ni dans le message de commit, ni ailleurs. Il
   introduit surtout une **incohérence entre les deux routes** : `/seasons` continue
   d'exposer `total_games`/`percentage` tandis que `/season/{id}/pourcent` expose
   désormais `total`/`pourcent`. Cette divergence a une conséquence mesurable
   aujourd'hui encore — voir section 5.2.

3. **Mélange français/anglais.** `$nbTotalGames`, `$pourcent`, `'match fini'`
   cohabitent avec `$games`, `getStatus()`. Le projet a depuis tranché pour
   l'anglais dans le code (le statut est aujourd'hui `'played'`), ce qui a imposé
   des passes de renommage ultérieures.

### Hunk 3 — `getSeasonGames()` : modification hors sujet

```diff
-    // TODO: need to be test with fake data
     #[Route('/season/{id}/games', name: 'app_season_games', methods: ['GET'])]
-    public function getSeasonGames(Season $season, DivisionRepository $divisionRepository, TeamStatRepository $teamStatRepository): JsonResponse
+    public function getSeasonGames(Season $season, DivisionRepository $divisionRepository, GameRepository $gameRepository): JsonResponse
     {
-        $games = [];
         $divisions = $divisionRepository->findBy(['season' => $season]);
         foreach ($divisions as $division) {
-            $teamsId = $teamStatRepository->findBy(['division' => $division]);
-            foreach ($teamsId as $teamId) {
-                $games[] = $teamId->getGames();
+            $games = $gameRepository->findBy(['division' => $division]);
+            foreach ($games as $game) {
+                $rep[] = [
+                    'id' => $game->getId(),
+                    'date' => $game->getDate()->format('d-m-Y'),
+                    ...
+                ];
             }
         }
-        return $this->json($games);
+        return $this->json($rep);
     }
```

**Commentaire.** Cette réécriture n'a **aucun lien** avec l'anomalie annoncée par
le message de commit. Elle est fonctionnellement souhaitable (interroger
`GameRepository` plutôt que de traverser `TeamStat`, sérialiser explicitement au
lieu de renvoyer des entités brutes), mais elle n'a pas sa place dans un commit de
correctif — et elle introduit deux défauts nouveaux :

- **`$rep` n'est jamais initialisé.** Si la saison ne comporte aucune division, ou
  aucune division ne comporte de match, `$rep` n'est jamais affecté. En PHP 8,
  `return $this->json($rep)` déclenche alors `Warning: Undefined variable $rep` et
  la route renvoie `null` au lieu du tableau vide attendu. La ligne
  `$games = [];` qui protégeait ce cas a précisément été supprimée par le diff.
- **`$game->getDate()->format(...)` sans garde.** La date d'un match est
  nullable ; un match non encore planifié provoque un appel de méthode sur `null`,
  donc une `Error` fatale et une réponse 500.

**Enseignement pour C4.2.2.** Un commit de correctif doit être **atomique** : une
anomalie, un diff, un critère de recette. Ici, un correctif d'une ligne est noyé
dans 45 lignes modifiées, ce qui rend le commit non relisible, non revertable
isolément, et fait entrer trois régressions dans le même mouvement. La discipline
Conventional Commits adoptée depuis par le projet (`api/cliff.toml`) impose cette
séparation : un `fix:` ne contient que le correctif ; les améliorations relèvent
d'un `refactor:` distinct.

## 3.3 Ce que le correctif n'a pas traité

| Point | État après `9fda6bd` |
|---|---|
| Défaut A (`+= count($games)`) | Corrigé sur les deux routes |
| Défaut B (`'match fini'`) | **Non traité** — corrigé 5 mois plus tard par `02b93b0` |
| Duplication du bloc de calcul | **Non traitée** — factorisée bien plus tard dans `calculateSeasonGameStats()` |
| Test de non-régression | **Absent** |
| Cohérence des clés de réponse entre les deux routes | **Aggravée** |

## 3.4 État actuel du code

La factorisation manquante a finalement été réalisée. `SeasonController` expose
aujourd'hui une méthode privée unique, ce qui rend structurellement impossible la
réapparition du défaut sur une seule des deux routes :

```php
/**
 * Calcule les statistiques des matchs pour une saison donnée
 */
private function calculateSeasonGameStats(Season $season, ...): array
{
    $totalGames = 0;
    $finishedGames = 0;
    $finishedStatus = $gameStatusRepository->findOneBy(['name' => 'played']);
    $divisions = $divisionRepository->findBy(['season' => $season]);

    foreach ($divisions as $division) {
        $games = $gameRepository->findBy(['division' => $division]);
        foreach ($games as $game) {
            $totalGames++;
            if ($game->getStatus() === $finishedStatus) {
                $finishedGames++;
            }
        }
    }

    $percentage = $totalGames > 0 ? ($finishedGames / $totalGames) * 100 : 0;

    return [
        'total_games' => $totalGames,
        'finished_games' => $finishedGames,
        'percentage' => $percentage
    ];
}
```

Les trois griefs de fond sont levés : incrémentation unitaire, `findOneBy` hissé
hors des boucles, calcul unique partagé par `GET /seasons` et
`GET /seasons/{id}/completion`. Le libellé de statut est passé à `'played'`.

---

# 4. Intervention du processus CI/CD

## 4.1 Constat factuel — ce qui s'est réellement passé en octobre 2024

Aucun élément de la chaîne d'intégration et de déploiement continu décrite au §5 de
`PROCESSUS_ANOMALIES.md` n'est intervenu, pour une raison simple : **aucun n'existait**.

| Maillon de la chaîne | Attendu | Réalité en octobre 2024 | Preuve |
|---|---|---|---|
| Issue GitHub | Fiche de consignation | Aucune | Aucune référence `#N` dans l'historique |
| Branche `fix/N-description` | Isolation du correctif | Commit direct sur la branche de travail | `git log` linéaire, sans merge |
| Commit `fix: … (#N)` | Conventional Commits | Format partiellement respecté (`fix(seasonController) :`), sans référence d'issue | Message du commit `9fda6bd` |
| Pull request « Closes #N » | Revue par un tiers | Aucune | Aucun commit de merge |
| CI : tests + lint + audit | Blocage si échec | Aucun workflow | Premier workflow : `cda1524`, 15/03/2026 |
| Tests automatisés | Non-régression | Aucun test dans le dépôt | Premier commit sur `tests/` : `8ebb84c`, 20/06/2025 |
| Release + `CHANGELOG.md` | Traçabilité | Aucun tag | Premier tag `v1.0.0`, 26/06/2025 |
| `/api/health` → version | Vérification post-déploiement | Endpoint inexistant | `HealthController` introduit en 2026 |

**Conséquence mesurable, et non théorique.** L'absence de test portant sur la valeur
retournée a produit trois effets vérifiables :

1. Le **défaut B est resté invisible** pendant 5 mois de plus. Un test affirmant
   « une saison dont tous les matchs sont joués retourne 100 % » aurait échoué au
   moment même du correctif A et révélé le défaut B dans la foulée.
2. Le correctif A a été **livré sans preuve d'effet** : l'affichage est resté à 0 %
   avant comme après, sans que personne ne le constate.
3. Les **régressions du hunk 3** (`$rep` non initialisé, date nullable) sont entrées
   en production sans obstacle. Une revue par pull request les aurait signalées ;
   un test fonctionnel sur `/season/{id}/games` avec une saison sans division les
   aurait bloquées.

## 4.2 Rejeu du même correctif dans la chaîne actuelle

Voici le déroulement complet du traitement de cette même anomalie avec le processus
aujourd'hui en place, en n'utilisant que des mécanismes réellement présents dans le
dépôt.

### Étape 1 — Consignation

Ouverture d'une issue via le template `api/.github/ISSUE_TEMPLATE/bug_report.yml`.
Les champs obligatoires du template — et notamment **Étapes de reproduction** — sont
bloquants : le format YAML de GitHub interdit la soumission d'une fiche incomplète.
La fiche produite est celle de la section 1. Labels appliqués : `type:bug`,
`severite:s3`, `composant:api`, `statut:a-trier`, puis `statut:confirme` après
reproduction locale.

### Étape 2 — Branche dédiée

```bash
git switch -c fix/42-pourcentage-avancement-saison
```

La nomenclature `fix/N-description` inscrit le numéro d'issue dans le nom de
branche, premier maillon de la chaîne de traçabilité.

### Étape 3 — Test de non-régression d'abord

Le test est écrit **avant** le correctif et doit échouer sur le code fautif. C'est
ce qui garantit qu'il teste bien l'anomalie et non le correctif. Il est ajouté à
`tests/Functional/Controller/SeasonControllerTest.php`, sur la base
`ApiTestCase` (SQLite, `.env.test`) — code complet en section 5.1.

```bash
php bin/phpunit --filter testSeasonCompletionCountsEachGameOnce
# → échec attendu : 613 !== 49
```

### Étape 4 — Correctif minimal

Une ligne, sur le seul périmètre de l'anomalie. Les améliorations connexes
(factorisation, renommage des clés, requête hissée hors boucle) font l'objet de
commits `refactor:` distincts, éventuellement d'une PR séparée.

```bash
php bin/phpunit --filter testSeasonCompletionCountsEachGameOnce   # → vert
make test                                                          # suite complète
make lint                                                          # syntaxe PHP
make security                                                      # audit des dépendances
```

### Étape 5 — Commit conventionnel

Le format est imposé par la configuration `git-cliff` du projet (`api/cliff.toml`),
qui alimente le `CHANGELOG.md`. Le type `fix` est retenu au changelog ;
`docs`, `test`, `chore`, `ci` et `style` en sont exclus.

```
fix(season): compter chaque match une seule fois dans le taux d'avancement

count($games) était évalué à chaque itération de la boucle interne, ce qui
ajoutait n² matchs au lieu de n pour une division de n matchs. Le taux
d'avancement des saisons était divisé par la taille moyenne des divisions
(613 au lieu de 49 sur la saison I).

Closes #42
```

Le pied `Closes #42` referme automatiquement l'issue à la fusion et matérialise le
lien issue ↔ commit ↔ release.

### Étape 6 — Pull request et contrôles automatiques

L'ouverture de la PR déclenche le workflow `.github/workflows/claude-code-review.yml`
(présent et versionné dans le dépôt), qui produit une revue automatique du diff.
Le workflow `claude.yml` permet en complément de solliciter une analyse à la
demande par mention dans un commentaire.

C'est ici que les défauts du commit historique auraient été arrêtés :

| Défaut de `9fda6bd` | Maillon qui l'aurait bloqué |
|---|---|
| Défaut B (`'match fini'`) | Test de non-régression sur la valeur (étape 3) |
| `$rep` non initialisé | Revue de PR + test fonctionnel sur saison vide |
| Date nullable non gardée | Revue de PR |
| N+1 (`findOneBy` en boucle) | Revue de PR |
| Renommage non documenté des clés | Revue de PR — hors périmètre d'un `fix:` |
| Périmètre du commit trop large | Revue de PR — commit non atomique |

### Étape 7 — Fusion et publication de version

Après fusion, le workflow `Release` (`.github/workflows/release.yml`) est déclenché
manuellement (`workflow_dispatch`, incrément `patch`). Il :

1. calcule le tag SemVer suivant à partir du dernier tag existant ;
2. régénère `CHANGELOG.md` via `git-cliff` et la configuration `cliff.toml` ;
3. commite (`chore(release): vX.Y.Z`), pose le tag annoté et le pousse ;
4. publie la release GitHub avec les notes de la seule nouvelle version.

Le déclenchement est manuel par choix documenté dans le workflow : plusieurs
correctifs étant souvent fusionnés le même jour, une release par fusion produirait
un journal illisible pour le staff SBL.

### Étape 8 — Déploiement

```bash
export APP_VERSION=$(git describe --tags --abbrev=0)
export APP_COMMIT=$(git rev-parse HEAD)
docker compose build api && docker compose up -d api
```

`APP_VERSION` est injectée à la construction de l'image : c'est elle qui sera
exposée par `/api/health` et attachée aux événements Sentry, fermant la boucle
« anomalie → correctif → version déployée ».

### Étape 9 — Vérification en production

Voir section 5.4.

## 4.3 Écarts entre le processus documenté et l'outillage réellement en place

Par honnêteté méthodologique, l'état du dépôt au moment de la rédaction est le
suivant.

**Versionné et opérationnel :**

- `.github/workflows/claude-code-review.yml` et `.github/workflows/claude.yml`
- Conventional Commits, appliqués depuis 2026
- Tests PHPUnit (unitaires, intégration, fonctionnels) et cibles `make test`,
  `make lint`, `make security`

**Présent dans l'arbre de travail mais non encore commité** (`git status` sur
`api/`) :

- `.github/workflows/release.yml`
- `.github/ISSUE_TEMPLATE/` (dont `bug_report.yml`, support de la section 1)
- `.github/dependabot.yml`, `cliff.toml`, `CHANGELOG.md`
- `src/Controller/HealthController.php`, `config/packages/sentry.yaml`,
  `src/Monolog/DiscordWebhookHandler.php`

**Écart de fond à combler.** Le §5 de `PROCESSUS_ANOMALIES.md` décrit un maillon
« CI : tests + lint + audit sécurité » **auquel ne correspond aucun fichier de
workflow**, ni sur `origin/main`, ni sur `origin/dev`, ni dans l'arbre de travail.
Les commandes existent (`make test`, `make lint`, `make security`) mais leur
exécution reste manuelle : rien n'empêche aujourd'hui de fusionner une PR dont les
tests échouent — c'est-à-dire exactement la défaillance qui a laissé passer
l'anomalie de 2024.

Remédiation minimale à mettre en place, workflow `.github/workflows/ci.yml`
déclenché sur `pull_request` :

| Étape | Commande | Effet sur ce cas |
|---|---|---|
| Installation | `composer install --no-interaction` | — |
| Syntaxe | `make lint` | — |
| Base de test | `make setup-test-db` | — |
| Tests | `make test` | Aurait bloqué le défaut B et les régressions du hunk 3 |
| Audit dépendances | `make security` | — |

Tant que ce workflow n'existe pas et que `release.yml` n'est pas commité, la chaîne
de la section 4.2 repose partiellement sur la discipline de l'auteur plutôt que sur
un mécanisme contraignant.

---

# 5. Vérification post-correction

## 5.1 Test de non-régression

Le test doit porter sur la **valeur métier**, pas sur la forme de la réponse. C'est
le point où le projet a historiquement échoué : le test existant se contente de
vérifier la présence des clés, ce qui ne détecte ni le défaut A, ni le défaut B.

Test à ajouter dans `tests/Functional/Controller/SeasonControllerTest.php` :

```php
/**
 * Non-régression — anomalie du 23/10/2024 (commit 9fda6bd).
 *
 * count($games) était évalué à chaque itération de la boucle interne :
 * une division de n matchs contribuait n² au total. Le jeu de données
 * ci-dessous utilise deux divisions de tailles différentes (3 et 2) :
 *   - attendu : 3 + 2                 = 5
 *   - avec le défaut : 3² + 2²        = 13
 * Une division d'un seul match ne détecterait pas l'anomalie (1² = 1).
 */
public function testSeasonCompletionCountsEachGameOnce(): void
{
    $season = $this->createSeasonWithDivisions([
        // division => [nombre de matchs joués, nombre de matchs à jouer]
        'D1' => [2, 1],
        'D2' => [1, 1],
    ]);

    $response = $this->jsonRequest(
        'GET',
        '/api/seasons/' . $season->getId() . '/completion'
    );

    $this->assertResponseIsSuccessful();
    $this->assertSame(5, $response['total_games']);      // et non 13
    $this->assertSame(3, $response['finished_games']);   // et non 0 (défaut B)
    $this->assertSame('60.00', $response['percentage']);
}

/**
 * Non-régression — défaut B : le libellé de statut recherché doit exister
 * en base. Un libellé absent renvoie null et fige finished_games à 0.
 */
public function testSeasonCompletionReaches100WhenAllGamesPlayed(): void
{
    $season = $this->createSeasonWithDivisions(['D1' => [3, 0]]);

    $response = $this->jsonRequest(
        'GET',
        '/api/seasons/' . $season->getId() . '/completion'
    );

    $this->assertSame('100.00', $response['percentage']);
}
```

Deux propriétés rendent ces tests efficaces :

- **des divisions de tailles différentes et supérieures à 1**, seule configuration
  dans laquelle `Σ n_d² ≠ Σ n_d` ;
- **une assertion sur la valeur exacte** (`assertSame`) et non sur la présence de
  la clé. C'est la différence entre un test qui aurait détecté l'anomalie et le
  test qui existe aujourd'hui.

## 5.2 Anomalie détectée lors de la rédaction de ce dossier

L'exécution de la suite existante révèle un défaut **actif**, conséquence directe du
renommage de clés introduit par le hunk 2 du commit `9fda6bd` (section 3.2) :

```
$ php bin/phpunit --filter testGetSeasonCompletion

PHPUnit 12.5.14 by Sebastian Bergmann and contributors.
Runtime:       PHP 8.5.9

F.                                                                  2 / 2 (100%)

There was 1 failure:

1) App\Tests\Functional\Controller\SeasonControllerTest::testGetSeasonCompletion
Failed asserting that an array has the key 'total'.

/api/tests/Functional/Controller/SeasonControllerTest.php:126

FAILURES!
Tests: 2, Assertions: 6, Failures: 1.
```

Le test attend les clés `total`, `finished`, `pourcent` — celles introduites par
`9fda6bd` sur l'ancienne route `/season/{id}/pourcent` — alors que
`getSeasonCompletion()` retourne aujourd'hui `total_games`, `finished_games`,
`percentage`. Le renommage non documenté de 2024 produit donc encore un test rouge
en 2026.

Ce test rouge est aussi la démonstration de l'écart identifié en 4.3 : **sans
workflow CI exécutant `make test` sur chaque pull request, une suite en échec peut
rester en l'état sans que rien ne le signale.**

*Cet élément est un constat, pas une correction : la modification du code de l'API
sort du périmètre de ce dossier documentaire.*

## 5.3 Vérification manuelle sur données réelles

Comparaison de la réponse de l'API à la volumétrie effective en base.

```bash
# Valeur retournée par l'API
curl -s "https://<API_DOMAIN>/api/seasons/1/completion" | jq '{total_games, finished_games, percentage}'
```

```sql
-- Valeur de référence, calculée directement en base
SELECT
    COUNT(*)                                         AS total_attendu,
    COUNT(*) FILTER (WHERE gs.name = 'played')       AS joues_attendus,
    ROUND(100.0 * COUNT(*) FILTER (WHERE gs.name = 'played') / NULLIF(COUNT(*), 0), 2)
                                                     AS pourcentage_attendu
FROM game g
JOIN division d   ON g.division_id = d.id
JOIN game_status gs ON g.status_id = gs.id
WHERE d.season_id = 1;
```

Les deux résultats doivent coïncider. Ce contrôle couvre simultanément les deux
défauts : le défaut A fait diverger `total_games`, le défaut B fige
`finished_games` à zéro.

Contrôle complémentaire ciblant spécifiquement le défaut A, indépendant de tout
statut :

```sql
-- Détecte la signature du défaut : Σ n² au lieu de Σ n
SELECT SUM(n) AS attendu, SUM(n * n) AS signature_du_defaut
FROM (
    SELECT COUNT(*) AS n
    FROM game g JOIN division d ON g.division_id = d.id
    WHERE d.season_id = 1
    GROUP BY d.id
) parDivision;
```

## 5.4 Vérification post-déploiement

```bash
# 1. La version déployée est bien celle qui porte le correctif
curl -s https://<API_DOMAIN>/api/health | jq '{version, commit, status}'

# 2. Le correctif produit l'effet attendu en production
curl -s https://<API_DOMAIN>/api/seasons | jq '.[] | {name, total_games, percentage}'
```

Le premier appel ferme la chaîne de traçabilité : il permet d'affirmer que le
correctif consigné dans l'issue #42, fusionné par la PR correspondante et publié
sous le tag `vX.Y.Z`, **est effectivement celui qui tourne**. C'est précisément
l'information qui manquait en 2024 et qui a permis au correctif `9fda6bd` d'être
considéré comme clos alors que le symptôme persistait.

## 5.5 Critères de recette

Le correctif n'est réputé livré que si **l'ensemble** de ces conditions est vérifié :

| # | Critère | Moyen de contrôle |
|---|---|---|
| 1 | Le test de non-régression échoue sur le code fautif et passe sur le code corrigé | `php bin/phpunit --filter testSeasonCompletionCountsEachGameOnce`, avant puis après |
| 2 | La suite complète est verte | `make test` |
| 3 | `total_games` de l'API est égal au `COUNT(*)` en base | Section 5.3 |
| 4 | Une saison intégralement jouée affiche 100 % | Section 5.1, second test |
| 5 | Le badge front bascule sur « terminé » sur une saison achevée | Contrôle visuel sur `SeasonsView.vue` |
| 6 | Les deux routes exposent des valeurs cohérentes entre elles | `GET /seasons` vs `GET /seasons/{id}/completion` |
| 7 | `/api/health` retourne la version portant le correctif | Section 5.4 |
| 8 | L'issue est fermée automatiquement par le pied `Closes #N` | GitHub |
| 9 | Le `CHANGELOG.md` de la version contient l'entrée `fix(season): …` | Release GitHub |

Le critère 4 est le plus important au regard de l'historique : c'est celui qui
manquait en 2024 et dont l'absence a permis de clore un correctif exact sans que
l'utilisateur en voie le moindre effet.

---

## Synthèse des enseignements

| Constat | Mécanisme de prévention |
|---|---|
| Un `//TODO: need to be tested` n'a jamais empêché personne de livrer | Workflow CI bloquant sur `pull_request` |
| Un défaut copié-collé se duplique plus vite qu'il ne se corrige | Factorisation du calcul, revue de PR |
| Un correctif exact peut être sans effet observable | Critère de recette formulé sur la valeur métier, pas sur le diff |
| Une anomalie silencieuse échappe à tous les canaux de collecte | Test de non-régression obligatoire pour toute anomalie sans trace en journal |
| Un commit de correctif non atomique fait entrer des régressions | Conventional Commits : `fix:` strictement limité au correctif |
| Sans lien issue ↔ commit ↔ tag ↔ version déployée, la clôture n'est pas vérifiable | Chaîne `Closes #N` → `git-cliff` → tag → `/api/health` |
