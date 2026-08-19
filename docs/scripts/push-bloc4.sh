#!/usr/bin/env bash
#
# Publication des branches Bloc 4 et du tag de version.
#
# Les branches `feat/bloc4-supervision` existent déjà dans les quatre dépôts :
# elles ont été créées depuis `origin/main` via des worktrees temporaires, qui
# partageaient le même répertoire `.git`. Les worktrees ont disparu, mais les
# branches et leurs commits sont bien présents dans chaque dépôt.
#
# Ce script se contente donc de : nettoyer les enregistrements de worktrees
# devenus obsolètes, pousser les branches, ouvrir les pull requests, publier le
# tag v2.0.0 et la release associée.
#
# Prérequis : CLI `gh` authentifiée (`gh auth status`).
# Usage     : bash docs/scripts/push-bloc4.sh

set -uo pipefail

BRANCHE="feat/bloc4-supervision"
RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v gh >/dev/null 2>&1; then
    echo "ERREUR : la CLI GitHub (gh) est introuvable." >&2
    echo "  macOS : brew install gh   |   Linux : voir https://cli.github.com" >&2
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "ERREUR : gh n'est pas authentifié. Lance d'abord : gh auth login" >&2
    exit 1
fi

CORPS_META="Active les mécanismes GitHub qui n'ont d'effet que depuis la branche par défaut :

- **Dependabot** — surveillance hebdomadaire des dépendances
- **Formulaire de consignation d'anomalie** — champs de reproduction bloquants
- **Workflow de release** — tag SemVer, CHANGELOG et release GitHub

Aucun code applicatif n'est modifié : cette branche ne contient que des fichiers
de configuration et de documentation. Le code de supervision (\`HealthController\`,
handler Monolog, heartbeat du bot) reste sur \`dev\` et sera fusionné par le
circuit habituel.

Référence : Bloc 4 — maintien en condition opérationnelle."

publier() {
    local depot="$1" titre="$2" corps="$3"
    local chemin="$RACINE/$depot"

    echo ""
    echo "=================================================="
    echo "  $(basename "$(git -C "$chemin" remote get-url origin)" .git)"
    echo "=================================================="

    cd "$chemin" || return 1

    # Les worktrees pointaient vers /tmp et n'existent plus : on retire les
    # enregistrements orphelins, sans quoi la branche resterait considérée
    # comme « déjà extraite ailleurs ».
    git worktree prune

    if ! git rev-parse --verify -q "$BRANCHE" >/dev/null; then
        echo "  IGNORÉ : la branche $BRANCHE est absente de ce dépôt." >&2
        return 1
    fi

    echo "  Commit : $(git log --oneline -1 "$BRANCHE")"
    echo "  Fichiers :"
    git diff --name-only origin/main "$BRANCHE" | sed 's/^/    + /'
    echo ""

    git push -u origin "$BRANCHE" || return 1

    gh pr create \
        --base main \
        --head "$BRANCHE" \
        --title "$titre" \
        --body "$corps" \
        2>/dev/null || echo "  (pull request déjà ouverte — $(gh pr view "$BRANCHE" --json url -q .url 2>/dev/null))"
}

publier "api" \
    "chore(bloc4): journal de versions, fiche de consignation et Dependabot" \
    "$CORPS_META"

publier "SBL-app" \
    "chore(bloc4): configuration Dependabot" \
    "Surveillance hebdomadaire des dépendances npm, Docker et GitHub Actions.
Les paquets fortement couplés (Vue, Vite) sont regroupés pour éviter des pull
requests bloquées en attente les unes des autres."

publier "bot" \
    "chore(bloc4): configuration Dependabot" \
    "Surveillance hebdomadaire des dépendances npm, Docker et GitHub Actions.
\`discord.js\` est volontairement exclu des groupes : cette bibliothèque suit les
dépréciations de l'API Discord et chaque montée justifie la lecture du journal
amont."

publier "." \
    "docs(bloc4): documentation du maintien en condition opérationnelle" \
    "Documentation du dispositif : supervision et sondes, processus de collecte et
de consignation des anomalies, journal des versions, mise à jour des dépendances,
stratégie de sauvegarde, et dossier complet d'une anomalie traitée.

Référence : Bloc 4 — maintien en condition opérationnelle."

# ---------------------------------------------------------------------------
# Tag de version
# ---------------------------------------------------------------------------
#
# `v1.0.0` (première mise en production) et `v1.1.0` (jalon qualité) existent
# déjà sur le dépôt distant et sont conservés tels quels. Seul `v2.0.0` est
# ajouté, sur le HEAD de `main` — le commit « Backend v2 » qui introduit
# l'authentification et rompt donc le contrat pour le frontend et le bot.

echo ""
echo "=================================================="
echo "  Tag et release v2.0.0"
echo "=================================================="
cd "$RACINE/api" || exit 1

git push origin v2.0.0

# Les notes sont lues sur la branche Bloc 4, et non dans le répertoire de
# travail : celui-ci est positionné sur `dev`, dont le CHANGELOG peut différer.
NOTES="$(git show "$BRANCHE:CHANGELOG.md" 2>/dev/null | awk '/^## \[2\.0\.0\]/{f=1} /^## \[1\.1\.0\]/{f=0} f')"

if [[ -z "$NOTES" ]]; then
    echo "  AVERTISSEMENT : notes introuvables sur la branche $BRANCHE." >&2
    NOTES="Backend v2 — authentification, résultats de match, notifications push.
Version majeure : déploiement coordonné du frontend et du bot nécessaire.
Détail complet dans CHANGELOG.md."
fi

gh release create v2.0.0 \
    --title "v2.0.0 — Backend v2" \
    --notes "$NOTES" \
    2>/dev/null || echo "  (release déjà publiée)"

echo ""
echo "-------------------------------------------------------------"
echo "Terminé. À enchaîner :"
echo ""
echo "  1. Fusionner les quatre pull requests"
echo "  2. Settings -> Code security : activer Dependabot sur les 4 dépôts"
echo "  3. bash docs/scripts/create-labels.sh"
echo "  4. Capturer la page des releases du dépôt api"
echo "-------------------------------------------------------------"
