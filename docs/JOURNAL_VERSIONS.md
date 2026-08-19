# Journal des versions et gestion des releases — SBL

> Référence : compétence **C4.3.2** — *Établir un journal des versions déployées en y intégrant la documentation des correctifs réalisés pour suivre les différentes évolutions réalisées sur le logiciel.*

---

## 1. Problème à résoudre

Le projet SBL est réparti sur quatre dépôts Git (`api`, `SBL-app`, `bot`, `infrastructure`) totalisant plus de 350 commits sur deux ans. Jusqu'à la mise en place décrite ici, il n'existait aucun moyen fiable de répondre à trois questions pourtant élémentaires lors du traitement d'une anomalie :

1. Quelle version du logiciel est actuellement déployée en production ?
2. Qu'est-ce qui a changé depuis la version précédente ?
3. Quel correctif précis a résolu tel bogue, et dans quelle version a-t-il été livré ?

L'absence de réponse à ces questions a un coût concret : face à une régression, la seule méthode disponible consistait à parcourir manuellement l'historique Git en croisant les dates avec les souvenirs de déploiement.

---

## 2. Dispositif retenu

### 2.1 Versionnage sémantique

Chaque dépôt applique le [Semantic Versioning](https://semver.org/lang/fr/) sous la forme `vMAJEURE.MINEURE.CORRECTIF` :

| Incrément | Signification pour SBL | Exemple |
|---|---|---|
| **MAJEURE** | Rupture de compatibilité de l'API consommée par le frontend ou le bot | Renommage d'un champ de réponse |
| **MINEURE** | Nouvelle fonctionnalité rétrocompatible | Ajout des brackets de playoff |
| **CORRECTIF** | Correction d'anomalie sans changement de contrat | Correction du calcul de pourcentage |

La distinction majeure/mineure a un sens opérationnel direct dans ce projet : l'API est consommée par deux clients indépendants (frontend Vue et bot Discord) déployés séparément. Une version majeure signale qu'un déploiement coordonné est nécessaire.

### 2.2 Convention de commit

Les messages suivent la spécification [Conventional Commits](https://www.conventionalcommits.org/fr/) :

```
<type>(<portée>): <description>

[corps optionnel]

[pied optionnel : Closes #42]
```

| Type | Effet sur la version | Section du journal |
|---|---|---|
| `feat` | Mineure | Ajouté |
| `fix` | Correctif | Corrigé |
| `perf` | Correctif | Performance |
| `refactor` | Correctif | Modifié |
| `security`, `deps` | Correctif | Sécurité |
| `docs`, `test`, `chore`, `ci`, `style` | Aucun | Exclu du journal |
| Suffixe `!` ou `BREAKING CHANGE` | Majeure | Rupture |

Les types `docs`, `test` et `chore` sont volontairement **exclus** du journal. Le journal de versions s'adresse en premier lieu au staff SBL : y faire figurer « mise à jour de la configuration ESLint » nuirait à la lisibilité sans apporter d'information exploitable. L'historique Git reste évidemment exhaustif pour l'usage technique.

### 2.3 Génération automatique

Le fichier `CHANGELOG.md` est produit par [`git-cliff`](https://git-cliff.org/) à partir des messages de commit, selon la configuration `api/cliff.toml`. Le workflow `.github/workflows/release.yml` enchaîne quatre étapes :

1. Calcul de la version suivante à partir du dernier tag existant
2. Génération du `CHANGELOG.md` par `git-cliff`
3. Création du tag Git annoté et commit du journal mis à jour
4. Publication de la release GitHub avec les notes de la version

**Pourquoi un déclenchement manuel plutôt qu'automatique à chaque fusion ?** Sur ce projet, plusieurs correctifs sont fréquemment fusionnés dans la même journée. Publier une release par fusion produirait des dizaines de versions ne contenant chacune qu'une seule ligne — un journal techniquement exact mais inexploitable par le client. Le déclenchement manuel permet de regrouper un ensemble cohérent d'évolutions, tout en conservant une génération du contenu entièrement automatique : le développeur décide *quand* publier, jamais *ce que* contient le journal.

### 2.4 Traçabilité de la version déployée

La version est injectée dans le conteneur API au build (`APP_VERSION`, `APP_COMMIT`) et exposée par l'endpoint de supervision :

```bash
curl -s https://<API_DOMAIN>/api/health | jq '{version, commit}'
```

```json
{
  "version": "v1.0.0",
  "commit": "a3f9c1d2"
}
```

Ce point est essentiel au traitement des anomalies : la fiche de consignation exige le renseignement de la version applicative, et cette commande permet de l'obtenir en une seconde plutôt que de la déduire de la date du dernier déploiement.

---

## 3. Reconstitution rétroactive

Le projet ayant démarré sans convention de commit ni tags, l'historique antérieur à `v1.0.0` a été reconstitué a posteriori. La méthode retenue :

1. Extraction de l'historique complet (`git log --reverse --format="%ad|%s"`)
2. Identification des **jalons fonctionnels** — les incréments effectivement livrés et validés avec le staff SBL lors des points mensuels, tels que documentés dans le suivi de projet
3. Regroupement des commits par jalon et rédaction des entrées au format Keep a Changelog

Cinq versions ont ainsi été reconstituées, de `v0.1.0` (mai 2024, premières entités et CRUD) à `v0.5.0` (avril 2025, statistiques d'équipe). Au-delà, le journal s'appuie sur des **tags Git réels** posés sur `main`, ce qui n'exige aucune reconstitution.

Le fichier `api/CHANGELOG.md` porte une mention explicite de cette frontière : présenter un historique reconstitué comme s'il avait été tenu au fil de l'eau serait trompeur, alors que distinguer les deux régimes permet au lecteur de savoir exactement ce qui est mesuré et ce qui est reconstruit.

### Correspondance entre versions et jalons du projet

| Version | Date | Jalon fonctionnel | Origine |
|---|---|---|---|
| v0.1.0 | 05/2024 | Modèle de données et CRUD de base | Reconstituée |
| v0.2.0 | 07/2024 | Refonte des routes, résolution CORS | Reconstituée |
| v0.3.0 | 11/2024 | Endpoints de consultation de saison | Reconstituée |
| v0.4.0 | 12/2024 | Inscriptions des équipes | Reconstituée |
| v0.5.0 | 04/2025 | Premier hébergement, statistiques d'équipe | Reconstituée |
| **v1.0.0** | 26/06/2025 | **Première mise en production** | **Tag réel** |
| **v1.1.0** | 19/07/2026 | **CI/CD, PHPStan, CS-Fixer, durcissement OWASP** | **Tag réel** |
| **v2.0.0** | 23/07/2026 | **Backend v2 — authentification, résultats, notifications** | **Tag réel** |
| *Non publié* | — | *Playoffs et clôture automatique de saison (branche `dev`)* | — |

`v2.0.0` est une version **majeure** : l'introduction de l'authentification sur
tous les endpoints d'écriture rompt le contrat pour le frontend Vue et le bot
Discord, imposant un déploiement coordonné. C'est exactement l'information que
le versionnage sémantique doit porter dans une architecture à plusieurs clients
indépendants.

---

## 4. Documentation des correctifs

Chaque correctif consigné dans le journal reste relié à son contexte d'origine par une chaîne de liens explicites :

```
Entrée CHANGELOG  →  commit (SHA)  →  Pull Request  →  Issue (fiche de consignation)
```

La configuration `cliff.toml` insère automatiquement dans chaque entrée le lien vers le commit et, lorsqu'il existe, vers la pull request. Le pied de commit `Closes #N` relie la pull request à la fiche de consignation de l'anomalie.

Concrètement, une ligne du journal telle que :

> - Correction du calcul de pourcentage d'avancement ([#47](https://github.com/SBL-app/api/pull/47)) ([a3f9c1d](https://github.com/SBL-app/api/commit/a3f9c1d))

permet de remonter en deux clics à la fiche de consignation initiale, qui contient les étapes de reproduction, l'impact utilisateur et l'analyse de la cause. C'est cette chaîne, et non le journal seul, qui constitue la documentation réelle des correctifs.

---

## 5. Procédure de publication

```bash
# 1. Vérifier que la branche main est à jour et la CI au vert
git checkout main && git pull

# 2. Déclencher la release depuis GitHub
#    Actions -> Release -> Run workflow -> choisir patch | minor | major

# 3. Déployer la version publiée sur le VPS
export APP_VERSION=v1.0.1
export APP_COMMIT=$(git rev-parse HEAD)
docker compose build api && docker compose up -d api

# 4. Vérifier que la version déployée correspond
curl -s https://<API_DOMAIN>/api/health | jq '{version, commit, status}'
```

L'étape 4 n'est pas une formalité : elle vérifie que le conteneur reconstruit est bien celui qui tourne. Un `docker compose up -d` sans `build` préalable redémarre silencieusement l'image précédente — erreur de déploiement classique que ce contrôle rend immédiatement visible.
