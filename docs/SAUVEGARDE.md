# Sauvegarde et restauration de la base de données — SBL

> Ce document décrit le dispositif de sauvegarde automatisée de PostgreSQL, la
> stratégie de rétention retenue, et la procédure de restauration — cette
> dernière ayant été exécutée et mesurée, non seulement rédigée.

---

## 1. Pourquoi ce dispositif

Le dossier de supervision (`docs/SUPERVISION.md`) a rendu visibles les pannes de
l'application. Il ne dit rien du risque qui n'est pas une panne : la **perte de
données**. C'était jusqu'ici le seul point de défaillance non couvert du projet.

La situation de départ tient en deux constats :

- **Un VPS unique, sans redondance.** Le disque du VPS héberge à la fois
  l'application et son unique exemplaire de données. Une défaillance matérielle,
  une erreur de manipulation sur le volume Docker, ou une suppression de VPS par
  l'hébergeur détruit l'intégralité de la ligue : saisons, équipes, effectifs,
  matchs et résultats.
- **Aucune protection contre l'erreur logique.** La sauvegarde ne couvre pas
  seulement la panne matérielle. Un `DELETE` sans clause `WHERE` lors d'une
  intervention, une migration Doctrine erronée, ou un bug applicatif effaçant
  des inscriptions sont des scénarios bien plus probables qu'une panne de
  disque — et le RAID de l'hébergeur, lui, réplique fidèlement l'erreur.

Un point mérite d'être posé d'emblée, car il conditionne la lecture du reste :
**la réplication n'est pas une sauvegarde**. Un miroir reproduit instantanément
la suppression comme il reproduit l'écriture. Ce qui protège d'une erreur
logique, c'est un état antérieur figé, conservé assez longtemps pour couvrir le
délai de détection de l'erreur. C'est exactement ce que dimensionne la stratégie
de rétention de la section 3.

### Objectifs de reprise

| Indicateur | Valeur retenue | Justification |
|---|---|---|
| **RPO** — perte de données maximale acceptable | 24 h | Une sauvegarde quotidienne. Pour une ligue amateur dont l'activité se concentre sur quelques soirées par semaine, perdre au pire une journée de saisie représente un volume ressaisissable à la main. Un RPO à l'heure exigerait de l'archivage WAL continu, disproportionné ici (voir §8). |
| **RTO** — durée maximale de remise en service | 30 min | Temps mesuré de la procédure §6, avec une marge large pour le diagnostic et la décision. La restauration elle-même se compte en secondes sur le volume actuel. |
| Fenêtre de conservation | 4 semaines | Couvre la découverte tardive d'une corruption (voir §3). |

---

## 2. Architecture retenue

```
                      ┌──────────────────────────────┐
                      │   Conteneur sbl-backup       │
                      │   crond → backup.sh          │
                      │   (image postgres:16-alpine) │
                      └───────────┬──────────────────┘
                                  │
      ┌───────────────────────────┼───────────────────────────┐
      │ 1. pg_dump                │ 3. restauration           │ 5. signal
      │ 2. sha256sum              │    de contrôle            │
      ▼                           ▼                           ▼
┌──────────────┐          ┌──────────────┐          ┌────────────────────┐
│  PostgreSQL  │◄─────────│ base jetable │          │   Uptime Kuma      │
│  (internal)  │  vérif.  │ sbl_verify_* │          │  sonde push 26 h   │
└──────────────┘          └──────────────┘          └────────────────────┘
      │                                                       │
      │ 4. écriture                                           │ échec
      ▼                                                       ▼
┌──────────────────────────────┐              ┌────────────────────────────┐
│  /backups (montage hôte)     │              │  Webhook Discord           │
│    daily/   7 dumps          │              │  #alertes-technique        │
│    weekly/  4 dumps          │              └────────────────────────────┘
│    failed/  dumps rejetés    │
└──────────────────────────────┘
```

Trois choix structurent cette architecture.

**Un conteneur dédié plutôt qu'un cron sur l'hôte.** Une tâche cron définie sur
le VPS vit en dehors du dépôt : elle n'est ni versionnée, ni reproductible, et
disparaît silencieusement lors d'une réinstallation du serveur. Le service
`backup` de `docker-compose.yml` est décrit avec le reste de l'infrastructure,
redémarre avec elle, et se reconstruit à l'identique sur une nouvelle machine.

**L'image dérive de `postgres:16-alpine`.** La version des outils clients doit
correspondre à celle du serveur : un `pg_dump` antérieur refuse de s'exécuter,
et un dump produit par une version majeure supérieure n'est pas restaurable.
Faire dériver l'image de celle du serveur rend cette contrainte automatique —
la mise à jour de PostgreSQL entraîne mécaniquement celle du client, dans le
même fichier.

**Le conteneur est raccordé à `internal` et à `web`.** `internal` lui donne
accès à PostgreSQL et à Uptime Kuma sans exposition externe. `web` ne sert qu'à
une chose : l'accès sortant vers `discord.com` pour la notification d'échec —
le réseau `internal` étant déclaré `internal: true`, il n'a aucun accès Internet.
Aucun label Traefik n'est déclaré : le service n'est joignable de nulle part.

---

## 3. Stratégie de rétention

| Niveau | Nombre conservé | Couverture temporelle |
|---|---|---|
| Quotidien | 7 | Les 7 derniers jours, jour par jour |
| Hebdomadaire | 4 | Les 4 dernières semaines (dump du dimanche promu) |

Ces deux chiffres répondent à deux risques distincts.

**Les 7 quotidiennes couvrent l'erreur détectée rapidement.** Une suppression
accidentelle, une migration ratée ou un bug de saisie sont constatés en quelques
heures à quelques jours. Une granularité au jour permet alors de revenir juste
avant l'incident, en perdant le minimum de données légitimes écrites depuis.

**Les 4 hebdomadaires couvrent l'erreur détectée tardivement.** C'est le cas de
la corruption silencieuse : un bug qui fausse progressivement des statistiques
d'équipe peut n'être remarqué qu'au bout de trois semaines. Sans rétention
longue, les sept sauvegardes quotidiennes contiendraient toutes la corruption —
elles ne serviraient à rien. Un mois de recul offre un point de comparaison
sain pour reconstituer les données correctes.

**Pourquoi pas davantage ?** Au-delà d'un mois, la valeur d'une sauvegarde
s'effondre : une base restaurée d'il y a deux mois manquerait tant de matchs
qu'une ressaisie complète serait nécessaire de toute façon. Le coût en espace
disque sur un VPS mutualisé ne se justifie plus.

**Coût réel en espace.** Les sauvegardes hebdomadaires sont créées par lien
physique (`ln`) et non par copie : tant qu'une sauvegarde existe dans les deux
répertoires, elle n'occupe l'espace qu'une fois. L'occupation maximale est donc
de 11 dumps distincts, et non 11 copies indépendantes.

Les valeurs sont paramétrables (`BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`,
`BACKUP_WEEKLY_DAY`) sans modification de code.

---

## 4. Format des dumps

```
/backups/daily/sbl-20260818-033000.dump         ← dump compressé
/backups/daily/sbl-20260818-033000.dump.sha256  ← empreinte
```

L'horodatage est au format `AAAAMMJJ-HHMMSS`, qui présente une propriété utile :
**l'ordre alphabétique des noms est l'ordre chronologique**. Un `ls` suffit à
lire la chronologie, et la rotation ne dépend pas des métadonnées du système de
fichiers, qu'une copie mal faite altérerait.

Le format retenu est le format `custom` de PostgreSQL (`pg_dump --format=custom`)
plutôt qu'un fichier SQL passé à `gzip`. Trois raisons :

1. **La compression est intégrée** (`--compress`, niveau 6 par défaut), sans
   dépendance à un outil externe ni fichier intermédiaire sur disque.
2. **Le dump contient une table des matières**, ce qui rend possible la
   vérification structurelle décrite en §5 sans restaurer quoi que ce soit.
3. **La restauration peut être sélective.** Lors d'un incident limité à une
   table — des résultats de matchs écrasés, par exemple — `pg_restore --table`
   restaure cette seule table sans toucher au reste de la base. Un dump SQL
   compressé imposerait de tout restaurer ou d'éditer le fichier à la main.

Le niveau de compression 6 est un compromis assumé : au-delà, le gain de taille
devient marginal alors que la durée du dump — et donc la charge sur PostgreSQL —
augmente nettement.

L'empreinte SHA-256 accompagne chaque dump. Elle est calculée depuis le
répertoire du dump, avec un chemin relatif, afin que `sha256sum -c` reste
vérifiable après recopie de l'archive vers un autre hôte (cf. §8).

---

## 5. Vérification d'intégrité

C'est le cœur du dispositif. Le mode de défaillance redouté d'une sauvegarde
n'est pas « elle a échoué » — cela se voit — mais **« elle a réussi et le
fichier est inexploitable »**. Une coupure de connexion en fin de dump, un
disque plein, ou une erreur de format produisent un fichier de taille plausible,
correctement horodaté, que personne ne remarque avant le jour de l'incident.

Chaque exécution enchaîne donc quatre contrôles, tous bloquants.

| # | Contrôle | Ce qu'il détecte | Coût |
|---|---|---|---|
| 1 | Taille minimale (1 Kio) | Dump vide, écriture interrompue au premier octet | Nul |
| 2 | Lecture de la table des matières (`pg_restore --list`) | Fichier tronqué, en-tête corrompu | Faible, sans solliciter le serveur |
| 3 | **Restauration effective dans une base jetable** | Corruption interne, contenu non restaurable | Quelques secondes de CPU serveur |
| 4 | Décompte des tables restaurées | Dump valide mais portant sur la mauvaise base, ou schéma amputé | Nul |

Le contrôle n° 3 est le seul qui prouve réellement quelque chose : le dump est
restauré dans une base temporaire `sbl_verify_<pid>`, créée puis supprimée à
chaque exécution. Les trois autres contrôles sont des filtres rapides placés en
amont pour éviter de mobiliser le serveur inutilement.

Deux détails d'implémentation conditionnent la validité de ce contrôle :

- `pg_restore --exit-on-error`. Sans cette option, `pg_restore` signale les
  erreurs mais se termine avec un **code de sortie nul** : une restauration
  partielle passerait pour un succès. C'est précisément le faux positif que la
  vérification est censée éliminer.
- Écriture sous `.part` puis renommage. Un dump interrompu ne porte jamais le
  nom d'un dump valide : il ne peut être ni promu en hebdomadaire, ni compté
  dans la rotation, ni sélectionné par `--latest` lors d'une restauration.

Un dump qui échoue à l'un de ces contrôles est déplacé dans `/backups/failed/`.
Il reste disponible pour le diagnostic, mais sort du décompte de la rotation :
une sauvegarde non vérifiée n'est jamais présentée comme une sauvegarde valide.

---

## 6. Procédure de restauration

> **Cette procédure a été exécutée**, pas seulement rédigée. Les résultats du
> test figurent en fin de section.

Le script `restore.sh` restaure par défaut dans une base **neuve**, jamais dans
la base de production. Ce n'est pas de la prudence excessive : c'est aussi la
bonne première étape d'un incident réel — on restaure à côté, on vérifie le
contenu, et seulement ensuite on bascule. Écraser la production exige le
drapeau explicite `--force`.

### 6.1 Inventaire des sauvegardes disponibles

```bash
docker compose exec backup restore.sh --list
```

### 6.2 Restauration de contrôle (sans risque)

Restaure la sauvegarde la plus récente dans une base `sbl_restore_<horodatage>`,
sans toucher à la production :

```bash
docker compose exec backup restore.sh --latest
```

Vérification du contenu restauré :

```bash
docker compose exec postgres psql -U sbl -d sbl_restore_<horodatage> -c \
  "SELECT (SELECT count(*) FROM users) AS utilisateurs, (SELECT count(*) FROM team) AS equipes, (SELECT count(*) FROM game) AS matchs;"
```

### 6.3 Restauration de la production après incident

**Cette opération détruit les données actuelles**, y compris celles écrites
depuis le dump choisi. Elle suppose une décision prise, pas un réflexe.

```bash
# 1. Arrêter les écritures : l'API et le scheduler, pas la base
docker compose stop api scheduler bot

# 2. Restaurer (le script demande confirmation par saisie du nom de la base)
docker compose exec backup restore.sh --latest --target sbl --force

# 3. Vérifier l'état de la base et des migrations
docker compose start api
curl -s https://<API_DOMAIN>/api/health | jq '{status, database, migrations}'

# 4. Rouvrir le service
docker compose start scheduler bot
```

L'ordre des étapes n'est pas indifférent. Arrêter l'API et le scheduler **avant**
la restauration évite qu'une requête en cours ne réécrive dans une base en cours
de reconstruction, et évite l'échec du `DROP DATABASE` sur connexion résiduelle
— le script ferme d'ailleurs lui-même les connexions restantes. Contrôler
`/api/health` **avant** de relancer le bot garantit qu'on ne rouvre pas le
service sur une base dont les migrations ne correspondent pas au code déployé.

### 6.4 Restauration d'une seule table

Pour un incident circonscrit (résultats de matchs écrasés, effectif supprimé),
restaurer toute la base ferait perdre les écritures légitimes des autres tables.
Le format `custom` permet de cibler :

```bash
docker compose exec backup pg_restore -h postgres -U sbl -d sbl \
  --data-only --table=game --exit-on-error /backups/daily/sbl-<horodatage>.dump
```

### 6.5 Vérification manuelle d'une empreinte

```bash
docker compose exec backup sh -c 'cd /backups/daily && sha256sum -c sbl-<horodatage>.dump.sha256'
```

### 6.6 Résultats du test de restauration

Test exécuté le 18/08/2026 sur le schéma du projet (`docker/postgres/init.sql`,
16 tables), avec un conteneur PostgreSQL 16 et l'image de sauvegarde du dépôt.

| Scénario testé | Résultat attendu | Résultat obtenu |
|---|---|---|
| Sauvegarde nominale | Dump vérifié, sonde notifiée | ✅ 141 objets, 16 tables vérifiées, 2 s |
| Rotation sur 5 exécutions (`KEEP_DAILY=3`) | 3 quotidiennes conservées | ✅ les plus anciennes supprimées, décompte stable |
| Promotion hebdomadaire | Lien physique dans `weekly/` | ✅ inode partagé (2 liens), rotation indépendante |
| PostgreSQL injoignable | Échec, alerte Discord, sonde `down` | ✅ sortie 1, notification émise |
| Contrôle de cohérence en échec | Dump déplacé dans `failed/`, alerte | ✅ dump isolé, sonde `down`, base de contrôle supprimée |
| Restauration dans une base neuve | 16 tables restaurées | ✅ 2 s |
| Restauration de production sans `--force` | Refus explicite | ✅ sortie 1, refus documenté |
| **Restauration de production avec `--force`** | Base ramenée à l'état du dump | ✅ ligne écrite après le dump absente, 3 saisons restaurées, 1 s |
| Dump altéré (1 octet modifié) | Refus avant restauration | ✅ empreinte SHA-256 non conforme, sortie 1 |

Le test le plus significatif est l'avant-dernier : une ligne a été écrite en base
**après** la prise du dump, puis la restauration a été lancée. La ligne a bien
disparu et le contenu du dump a été retrouvé à l'identique — c'est ce qui
distingue une restauration réelle d'une restauration qui « s'est terminée sans
erreur ».

Ce test est à rejouer après toute mise à jour majeure de PostgreSQL, ainsi
qu'une fois par trimestre — une procédure de restauration qui n'a pas été
exécutée depuis un an n'est plus une procédure, c'est une hypothèse.

---

## 7. Supervision, alerte et diagnostic

Le dispositif de signalement s'appuie sur les deux canaux déjà en place
(`docs/SUPERVISION.md` §5), avec une répartition des rôles précise.

| Canal | Ce qu'il signale | Mode de panne couvert |
|---|---|---|
| Webhook Discord `#alertes-technique` | L'**échec** d'une sauvegarde, avec l'étape et le message d'erreur | La sauvegarde s'est exécutée et a échoué |
| Sonde push Uptime Kuma | La **réussite** d'une sauvegarde | La sauvegarde ne s'est pas exécutée du tout |

Cette dualité est le point important. Un script qui échoue peut alerter ; un
script qui **ne s'exécute plus** est muet par nature — conteneur arrêté, crond
mort, pile non relancée après un redémarrage du VPS. C'est le mode de panne le
plus probable d'une tâche planifiée, et le seul que l'alerte par webhook ne peut
structurellement pas détecter. La sonde push inverse la logique : c'est
l'**absence** de signal qui déclenche l'alerte.

### 7.1 Sonde push Uptime Kuma

| Paramètre | Valeur |
|---|---|
| Type | Push |
| Intervalle (période de grâce) | **93 600 s (26 h)** |
| Tentatives avant alerte | 1 |
| Notification rattachée | Discord `#alertes-technique` |

Le choix de 26 heures se déduit de la fréquence : une sauvegarde quotidienne
émet un signal toutes les 24 h. Un seuil à 24 h exactement produirait une alerte
à chaque exécution un peu plus lente que la veille. Les deux heures de marge
absorbent la variation de durée du dump, un redémarrage de la pile, et surtout
le changement d'heure saisonnier. À l'inverse, un seuil à 48 h laisserait passer
une journée entière sans sauvegarde sans que personne ne le sache.

La durée de la sauvegarde est transmise comme « latence » de la sonde. Uptime
Kuma en trace la courbe, ce qui rend visible une dérive progressive du temps de
dump à mesure que la base grossit — bien avant qu'elle ne devienne un problème.

En cas d'échec, le script pousse en plus un statut `down` immédiat : l'alerte ne
dépend donc pas de l'expiration des 26 h.

### 7.2 Notification Discord d'échec

L'embed reprend la mise en forme et les couleurs du handler Monolog de l'API
(`api/src/Monolog/DiscordWebhookHandler.php`) : les alertes issues de sources
différentes restent lisibles comme un flux unique. Il contient l'étape en échec,
le message d'erreur remonté par l'outil PostgreSQL, l'hôte, et le chemin du dump
rejeté.

Comme pour le handler applicatif, `ALERT_DISCORD_WEBHOOK` vide rend la
notification inerte : en développement local, le service démarre sans
configuration d'alerte.

### 7.3 Diagnostic d'un échec

```bash
# 1. Journal du service (les exécutions cron y sont redirigées)
docker compose logs --tail=100 backup

# 2. Rejouer une sauvegarde à la demande, en observant la sortie
docker compose exec backup backup.sh

# 3. Inspecter les dumps rejetés
docker compose exec backup ls -l /backups/failed/

# 4. Espace disque — cause la plus fréquente
df -h /var/lib/docker
```

| Étape en échec | Causes les plus probables |
|---|---|
| `connexion à PostgreSQL` | Conteneur `postgres` arrêté, mot de passe modifié sans mise à jour du `.env` |
| `génération du dump` | Disque plein, version cliente incompatible après mise à jour de PostgreSQL |
| `restauration de contrôle` | Dump corrompu (disque), droits `CREATEDB` retirés à l'utilisateur |
| `contrôle de cohérence` | Base ciblée vide ou incorrecte, schéma amputé par une migration ratée |

---

## 8. Limites connues et axes d'amélioration

Il faut être explicite sur ce que ce dispositif **ne couvre pas**.

**Les sauvegardes résident sur la machine sauvegardée.** C'est la limite
principale. Le montage hôte (`BACKUP_HOST_PATH`) protège de la corruption
logique, de l'erreur humaine et de la perte du volume Docker — soit la grande
majorité des incidents réels — mais **pas de la perte du VPS lui-même**. Tant
que cette copie distante n'existe pas, le point de défaillance unique est réduit,
pas éliminé.

Le montage hôte a précisément été choisi (plutôt qu'un volume Docker nommé) pour
que cette recopie soit triviale à ajouter, sans modifier l'application :

```bash
# À planifier sur l'hôte, après l'horaire de sauvegarde
rclone sync /chemin/vers/backups distant:sbl-backups --max-age 30d
```

Le chiffrement de l'archive (`age`, `gpg`) devient alors nécessaire : les dumps
contiennent des identifiants Discord et des adresses de courriel.

**Le RPO reste de 24 h.** Un incident survenant à 22 h fait perdre la soirée de
match. Descendre sous ce seuil suppose l'archivage WAL continu (*point-in-time
recovery*), qui apporte une reprise à la seconde près mais impose un stockage
d'archives permanent et une procédure de restauration nettement plus complexe.
Disproportionné au regard du volume actuel et du caractère ressaisissable des
données.

**La vérification prouve la restaurabilité technique, pas la cohérence
métier.** Un dump peut être parfaitement restaurable et contenir des données
déjà corrompues par un bug applicatif. C'est le rôle de la rétention à quatre
semaines (§3) de laisser une porte de sortie dans ce cas.

**Le dump s'exécute sur l'instance de production.** Sur le volume actuel
(quelques dizaines de Mio, dump en 2 s) l'impact est négligeable, et l'horaire
de 3 h 30 le place hors de la fenêtre d'activité. Cette hypothèse serait à
revoir si la base croissait d'un ordre de grandeur.

---

## 9. Mise en œuvre

### 9.1 Variables d'environnement

```dotenv
TZ=Europe/Paris
BACKUP_HOST_PATH=./backups
BACKUP_CRON=30 3 * * *
BACKUP_KEEP_DAILY=7
BACKUP_KEEP_WEEKLY=4
BACKUP_WEEKLY_DAY=7
BACKUP_COMPRESSION_LEVEL=6
BACKUP_RUN_ON_START=false
BACKUP_UPTIME_KUMA_PUSH_URL=http://uptime-kuma:3001/api/push/<TOKEN>
ALERT_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...
```

L'horaire de 3 h 30 est choisi hors de la fenêtre d'activité de la ligue (les
soirées de match) et décalé des horaires ronds, où se concentrent les tâches
planifiées de l'hébergeur.

`TZ` n'est pas cosmétique : sans lui le conteneur travaille en UTC et l'horaire
réel de sauvegarde se décale d'une heure entre l'hiver et l'été.

### 9.2 Activation

- [ ] Renseigner les variables ci-dessus dans `.env`
- [ ] Créer la sonde *Push* dans Uptime Kuma — intervalle **93 600 s**, une seule
      tentative, notification Discord rattachée
- [ ] Reporter le token dans `BACKUP_UPTIME_KUMA_PUSH_URL`
- [ ] Démarrer le service :
      ```bash
      docker compose up -d --build backup
      ```
- [ ] Déclencher une première sauvegarde et observer la chaîne complète :
      ```bash
      docker compose exec backup backup.sh
      ```
- [ ] Vérifier que la sonde Uptime Kuma est passée au vert
- [ ] Exécuter la restauration de contrôle (§6.2) et conserver la sortie
- [ ] Ajouter la sonde de sauvegarde à la status page publique

### 9.3 Test de la chaîne d'alerte

Comme pour la supervision, un dispositif d'alerte non testé est une hypothèse.
La chaîne se valide en provoquant un échec réel :

```bash
# Provoquer l'échec : base injoignable
docker compose stop postgres
docker compose exec backup backup.sh   # doit sortir en erreur

# → une alerte doit apparaître dans #alertes-technique
# → la sonde de sauvegarde doit passer au rouge

docker compose start postgres
docker compose exec backup backup.sh   # doit réussir et repasser la sonde au vert
```

---

## Références

| Fichier | Rôle |
|---|---|
| `docker/backup/Dockerfile` | Image de sauvegarde (client PostgreSQL + curl) |
| `docker/backup/entrypoint.sh` | Planification crond, propagation de l'environnement |
| `docker/backup/backup.sh` | Dump, vérification, rotation, signalement |
| `docker/backup/restore.sh` | Restauration outillée et garde-fous |
| `docker/backup/notify.sh` | Webhook Discord et sonde push Uptime Kuma |
| `docs/SUPERVISION.md` | Dispositif de supervision dont ce document reprend les canaux |
