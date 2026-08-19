# Dossiers d'anomalies traitées

Ce répertoire rassemble les dossiers de traitement complet d'anomalies réelles du
projet SBL, de leur consignation à la vérification de leur correctif en production.

Il constitue le pendant applicatif des deux documents de processus :

| Document | Objet | Compétence |
|---|---|---|
| [`../PROCESSUS_ANOMALIES.md`](../PROCESSUS_ANOMALIES.md) | Processus de collecte et de consignation | C4.2.1 |
| Ce répertoire | Traitement effectif d'une anomalie de bout en bout | C4.2.2 |

## Nomenclature

`AAAA-MM-JJ-description-courte.md` — la date est celle du **commit de correction**.

## Structure d'un dossier

1. **Fiche de consignation** — reprise champ par champ du template
   `api/.github/ISSUE_TEMPLATE/bug_report.yml`
2. **Analyse de la cause racine** — mécanisme technique et cause organisationnelle
3. **Correctif appliqué** — diff commenté, y compris ce que le correctif n'a pas traité
4. **Intervention du processus CI/CD** — de l'issue au déploiement
5. **Vérification post-correction** — tests, contrôles manuels, critères de recette

## Dossiers

| Date | Anomalie | Composant | Sévérité | Commit correctif |
|---|---|---|---|---|
| 23/10/2024 | [Pourcentage d'avancement de saison erroné](./2024-10-23-pourcentage-avancement-saison.md) | API — `SeasonController` | S3 | `9fda6bd` |

## Principe de rédaction

Ces dossiers s'appuient exclusivement sur des éléments vérifiables : historique Git,
contenu réel des commits, jeux de données de production, sorties de commandes
réellement exécutées. Lorsqu'un élément n'est pas déductible des sources
disponibles — typiquement les champs d'une fiche reconstituée a posteriori, pour une
anomalie antérieure à la mise en place du processus — il est signalé comme tel plutôt
que comblé par une hypothèse. Les écarts entre le processus documenté et l'outillage
effectivement en place sont explicités.
