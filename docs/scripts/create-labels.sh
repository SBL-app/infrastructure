#!/usr/bin/env bash
#
# create-labels.sh — Crée (ou met à jour) les labels GitHub du projet SBL
# sur tous les dépôts de l'organisation.
#
# Nomenclature : docs/PROCESSUS_ANOMALIES.md, section 4 « Nomenclature des labels ».
#
# Le script est idempotent : `gh label create --force` crée le label s'il
# n'existe pas, et met à jour couleur + description s'il existe déjà.
#
# Usage :
#   ./docs/scripts/create-labels.sh                  # tous les dépôts par défaut
#   ./docs/scripts/create-labels.sh api bot          # dépôts ciblés
#   ORG=autre-org ./docs/scripts/create-labels.sh    # autre organisation
#   DRY_RUN=1 ./docs/scripts/create-labels.sh        # affiche sans exécuter
#
# Prérequis : gh CLI authentifié avec le scope `repo` sur l'organisation.

set -euo pipefail

ORG="${ORG:-SBL-app}"
DRY_RUN="${DRY_RUN:-0}"

DEFAULT_REPOS=(api SBL-app bot infrastructure)

# ---------------------------------------------------------------------------
# Définition des labels : "nom|couleur|description"
#
# Palette — une teinte par famille :
#   type:      bleu    (nature de l'élément)
#   severite:  rouge   (dégradé, s1 = le plus foncé = le plus grave)
#   composant: violet  (base de code concernée)
#   statut:    vert    (avancement, du clair au foncé)
# ---------------------------------------------------------------------------
LABELS=(
  # type: — bleu
  "type: bug|0B4F9E|Dysfonctionnement constaté par rapport au comportement attendu"
  "type: feature|1D76DB|Nouvelle fonctionnalité ou évolution"
  "type: deps|4C9AFF|Mise à jour de dépendances"
  "type: dette|7FB8FF|Dette technique, refactorisation"
  "type: securite|A9D2FF|Vulnérabilité ou durcissement de sécurité"

  # severite: — rouge dégradé (s1 le plus foncé)
  "severite: s1|6E0000|Critique — service indisponible ou perte de données"
  "severite: s2|B60205|Majeure — fonctionnalité essentielle dégradée"
  "severite: s3|E25555|Mineure — contournement possible"
  "severite: s4|F5A9A9|Cosmétique — sans impact fonctionnel"

  # composant: — violet
  "composant: api|4B14B8|API Symfony"
  "composant: front|6B33E0|Frontend Vue 3"
  "composant: bot|8C5CF0|Bot Discord"
  "composant: infra|AD8AF5|Docker, Traefik, CI/CD"
  "composant: bdd|CBB4FA|PostgreSQL, migrations Doctrine"

  # statut: — vert (du clair au foncé selon l'avancement)
  "statut: a-trier|D4EDBC|En attente de triage"
  "statut: confirme|9BD46F|Anomalie reproduite et confirmée"
  "statut: non-reproductible|8A9A8A|Non reproductible en l'état"
  "statut: en-cours|2EA043|Correction en cours de développement"
  "statut: en-recette|17692F|Correctif déployé, en attente de validation"
)

# ---------------------------------------------------------------------------

command -v gh >/dev/null 2>&1 || {
  echo "Erreur : la CLI gh est introuvable. Voir https://cli.github.com/" >&2
  exit 1
}

gh auth status >/dev/null 2>&1 || {
  echo "Erreur : gh n'est pas authentifié. Lancer 'gh auth login'." >&2
  exit 1
}

if [ "$#" -gt 0 ]; then
  REPOS=("$@")
else
  REPOS=("${DEFAULT_REPOS[@]}")
fi

created=0
failed=0

for repo in "${REPOS[@]}"; do
  # Autorise soit "api" soit "org/api" en argument.
  case "$repo" in
    */*) full_repo="$repo" ;;
    *)   full_repo="${ORG}/${repo}" ;;
  esac

  echo "=== ${full_repo} ==="

  if ! gh repo view "$full_repo" >/dev/null 2>&1; then
    echo "  ! dépôt inaccessible, ignoré" >&2
    failed=$((failed + 1))
    continue
  fi

  for entry in "${LABELS[@]}"; do
    IFS='|' read -r name color description <<<"$entry"

    if [ "$DRY_RUN" = "1" ]; then
      echo "  [dry-run] ${name} (#${color})"
      continue
    fi

    # --force : crée le label ou met à jour couleur/description s'il existe.
    if gh label create "$name" \
        --repo "$full_repo" \
        --color "$color" \
        --description "$description" \
        --force >/dev/null 2>&1; then
      echo "  ✓ ${name}"
      created=$((created + 1))
    else
      echo "  ✗ ${name}" >&2
      failed=$((failed + 1))
    fi
  done
done

echo
echo "Terminé : ${created} label(s) traité(s), ${failed} échec(s)."
[ "$failed" -eq 0 ]
