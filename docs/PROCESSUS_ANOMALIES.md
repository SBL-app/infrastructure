# Processus de collecte et de consignation des anomalies — SBL

> Référence : compétence **C4.2.1** — *Consigner les anomalies détectées en élaborant un processus de collecte et consignation, en utilisant des outils de collecte et en y intégrant toutes les informations pertinentes, afin de déterminer le correctif à mettre en place.*

---

## 1. Principe directeur

Un processus de collecte n'a de valeur que s'il capte les anomalies **que personne ne signale**. Dans le cas de SBL, l'expérience du projet a montré que les remontées spontanées sont massivement biaisées : les joueurs signalent ce qui les bloque visiblement (page blanche, bouton inopérant) mais jamais ce qui échoue en silence (rappel de match non envoyé, notification push perdue, tâche planifiée non exécutée).

Le processus repose donc sur **trois canaux d'entrée complémentaires**, chacun couvrant un angle mort des deux autres, convergeant vers un point de consignation unique.

---

## 2. Canaux de collecte

```
   ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
   │  1. AUTOMATIQUE    │   │  2. SUPERVISION    │   │  3. HUMAIN         │
   │  Monolog + handler │   │  Uptime Kuma       │   │  Staff SBL,        │
   │  Discord / e-mail  │   │  (6 sondes)        │   │  joueurs (Discord) │
   └─────────┬──────────┘   └─────────┬──────────┘   └─────────┬──────────┘
             │                        │                        │
             │  exceptions PHP,       │  indisponibilité,      │  comportement
             │  erreurs 5xx           │  latence, migrations   │  inattendu
             │                        │                        │
             └────────────────────────┼────────────────────────┘
                                      ▼
                        ┌─────────────────────────────┐
                        │      TRIAGE (< 24 h)        │
                        │  Reproduction · Sévérité    │
                        │  Qualification              │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │   FICHE DE CONSIGNATION     │
                        │  GitHub Issue (template)    │
                        └──────────────┬──────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │  Correction · CI/CD · Recette│
                        └─────────────────────────────┘
```

### Canal 1 — Collecte automatique (erreurs applicatives)

L'API Symfony publie ses erreurs via Monolog selon une chaîne de handlers configurée dans `config/packages/monolog.yaml` :

| Handler | Rôle |
|---|---|
| `main` (rotating_file, 14 j) | Journal complet, base du diagnostic a posteriori |
| `error` (rotating_file, 30 j) | Erreurs isolées, rétention longue |
| `discord_buffer` → `discord_dedup` → `discord` | Notification temps réel sur `#alertes-technique` |
| `mail_buffer` → `mail_dedup` → `mail_sender` | Canal de secours si Discord est indisponible |

Deux mécanismes évitent la saturation du canal, qui est le principal facteur d'échec d'un dispositif de collecte :

- **`fingers_crossed`** — rien n'est émis tant qu'aucune erreur ne survient. Dès qu'une erreur apparaît, les 30 messages de contexte qui la précèdent sont transmis avec elle, ce qui fournit la séquence ayant conduit à l'anomalie plutôt que l'erreur seule.
- **`deduplication` (300 s)** — une même anomalie déclenchée cent fois en cinq minutes ne produit qu'une seule notification.

Les codes 404 et 405 sont exclus : ils traduisent une URL erronée, pas un défaut applicatif.

Le handler Discord (`src/Monolog/DiscordWebhookHandler.php`) transmet le message, la classe d'exception, le fichier et la ligne d'origine, ainsi que **la version applicative déployée** — information indispensable pour relier l'anomalie à une entrée du journal de versions.

### Canal 2 — Supervision (indisponibilité et dégradation)

Les six sondes Uptime Kuma décrites dans [`SUPERVISION.md`](./SUPERVISION.md) couvrent ce que Monolog ne peut structurellement pas voir : une application qui ne démarre plus n'émet aucun log. Ce canal détecte les pannes d'infrastructure, les dégradations de performance et les déploiements incomplets.

### Canal 3 — Remontées humaines

Le staff SBL et les joueurs signalent les anomalies sur le canal Discord `#bugs`. Ces remontées sont par nature incomplètes — « ça marche pas », « j'ai eu une erreur hier » — et c'est précisément le rôle du triage que de les transformer en fiches exploitables.

---

## 3. Triage

Toute anomalie entrante est traitée sous 24 heures selon quatre étapes.

**1. Reproduction.** Tenter de reproduire l'anomalie en environnement local. Une anomalie non reproductible n'est pas fermée : elle est consignée avec la mention correspondante et l'instrumentation est renforcée sur la zone concernée. Fermer un ticket non reproductible revient à attendre qu'il revienne, en ayant perdu le contexte initial.

**2. Qualification de la sévérité.**

| Niveau | Définition | Prise en charge | Correction cible |
|---|---|---|---|
| **S1 — Critique** | Service indisponible ou perte de données, aucun contournement | Immédiate | < 24 h |
| **S2 — Majeure** | Fonctionnalité majeure inutilisable, contournement complexe | < 24 h | < 1 semaine |
| **S3 — Mineure** | Fonctionnalité secondaire dégradée, contournement simple | < 1 semaine | Prochain jalon |
| **S4 — Cosmétique** | Défaut d'affichage ou de confort | Backlog | Opportuniste |

La sévérité est déterminée par l'**impact utilisateur**, non par la difficulté technique. Une faute d'orthographe sur la page d'accueil reste S4 même si sa correction prend dix secondes ; une erreur bloquant la saisie des résultats la veille d'une échéance est S1 même si la cause est triviale.

**3. Consignation.** Création de la fiche via le template GitHub (section 4).

**4. Priorisation.** Placement dans GitHub Projects, en arbitrage avec les évolutions en cours.

---

## 4. Fiche de consignation

La fiche est matérialisée par un **template d'issue GitHub** (`api/.github/ISSUE_TEMPLATE/bug_report.yml`) dont les champs obligatoires garantissent la présence des informations nécessaires à la reproduction. Le format YAML de GitHub permet de rendre des champs bloquants : une fiche incomplète ne peut pas être soumise, ce qu'un simple template Markdown ne permettrait pas.

| Champ | Obligatoire | Finalité |
|---|---|---|
| Source de la détection | Oui | Mesurer l'efficacité relative des trois canaux |
| Sévérité | Oui | Déterminer le délai de prise en charge |
| Composant concerné | Oui | Router vers la bonne base de code |
| Version applicative | Oui | Relier au journal de versions, identifier la release fautive |
| Environnement | Oui | Distinguer une anomalie de production d'un artefact local |
| Contexte d'apparition | Oui | Identifier le déclencheur (déploiement, profil utilisateur) |
| **Étapes de reproduction** | Oui | Champ central : sans lui, aucune correction fiable |
| Comportement attendu | Oui | Définir le critère de recette du correctif |
| Comportement constaté | Oui | Caractériser l'écart |
| Lien Sentry | Non | Stack trace complète si disponible |
| Journaux | Non | Extrait `docker compose logs` ou console navigateur |
| Impact utilisateurs | Oui | Alimenter l'arbitrage de priorisation |
| Analyse et piste de correction | Non | Renseigné au triage |

### Nomenclature des labels

| Préfixe | Valeurs | Usage |
|---|---|---|
| `type:` | `bug`, `feature`, `dette`, `securite` | Nature de l'élément |
| `severite:` | `s1`, `s2`, `s3`, `s4` | Gravité, alimente le tri |
| `composant:` | `api`, `front`, `bot`, `infra`, `bdd` | Base de code concernée |
| `statut:` | `a-trier`, `confirme`, `non-reproductible`, `en-cours`, `en-recette` | Avancement |

Le préfixage rend le filtrage lisible dans GitHub Projects et évite la prolifération de labels redondants observée en début de projet.

---

## 5. Traçabilité de bout en bout

Chaque anomalie est traçable de sa détection à son correctif déployé, sans rupture de chaîne :

```
Alerte Discord / Sonde Kuma / Retour staff
        │
        ▼
Issue GitHub #N  ──────────────────────────┐
        │                                   │
        ▼                                   │
Branche fix/N-description                   │
        │                                   │
        ▼                                   │
Commit « fix: … (#N) »  ← Conventional Commits
        │                                   │
        ▼                                   │
Pull Request « Closes #N »                  │
        │                                   │
        ▼                                   │
CI : tests + lint + audit sécurité          │
        │                                   │
        ▼                                   │
Merge sur main → release automatique        │
        │                                   │
        ▼                                   │
CHANGELOG.md + GitHub Release  ◄────────────┘
        │
        ▼
Déploiement → /api/health expose la nouvelle version
```

Cette chaîne est ce qui permet, face à une anomalie remontée en production, de répondre en quelques minutes à trois questions : quelle version est déployée (`/api/health`), qu'est-ce qui a changé depuis la précédente (`CHANGELOG.md`), et quel commit précis a introduit la régression (lien issue ↔ commit).

---

## 6. Indicateurs de suivi du processus

| Indicateur | Cible | Source |
|---|---|---|
| Délai de triage | < 24 h | Écart création → label `statut:confirme` |
| Taux de reproduction | > 80 % | Ratio `confirme` / (`confirme` + `non-reproductible`) |
| Délai de correction S1 | < 24 h | Écart création → merge |
| Part des anomalies détectées automatiquement | > 50 % | Champ « Source de la détection » |

Le dernier indicateur est le plus révélateur de la maturité du dispositif : si la majorité des anomalies continue d'être signalée par les utilisateurs, c'est que la collecte automatique reste insuffisante.
