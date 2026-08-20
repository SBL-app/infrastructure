# Système de supervision et d'alerte — SBL

> Référence : compétence **C4.1.2** — *Concevoir un système de supervision et d'alerte en déterminant le périmètre de supervision et en identifiant les indicateurs de suivi pertinents, en mettant en place des sondes, en configurant la modalité des signalements afin de garantir une disponibilité permanente du logiciel.*

---

## 1. Périmètre de supervision

L'application SBL n'est pas un service monolithique : c'est un ensemble de composants hétérogènes dont la défaillance a des conséquences différentes pour les utilisateurs. Le périmètre de supervision a donc été défini composant par composant, en partant de la question « quelle panne l'utilisateur final subirait-il sans que je le sache ? ».

| Composant | Rôle fonctionnel | Impact d'une panne | Supervisé |
|---|---|---|---|
| Frontend Vue 3 | Interface joueurs et staff | Site inaccessible — panne totale perçue | Oui |
| API Symfony | Logique métier, authentification | Site affiché mais aucune donnée — panne perçue comme totale | Oui |
| PostgreSQL | Persistance | Panne API en cascade | Oui |
| Bot Discord | Commandes, rappels de matchs | Panne silencieuse : personne ne signale un rappel non reçu | Oui |
| Scheduler Symfony | Rappels et deadlines automatiques | Panne silencieuse | Oui (indirect) |
| Certificat TLS | Chiffrement | Blocage navigateur à l'expiration | Oui |
| Traefik | Routage, terminaison TLS | Panne totale | Oui (indirect) |

Deux composants méritent une justification particulière.

**Le bot Discord** est le cas le plus critique en matière de détection. Une panne du frontend est signalée en quelques minutes par les joueurs ; une panne du bot ne l'est jamais, car un rappel de match qui n'arrive pas ne génère aucune plainte — il génère simplement des résultats de matchs non saisis, constatés une semaine plus tard. C'est précisément le type d'anomalie que la supervision doit rendre visible.

**Le scheduler** est supervisé indirectement : il partage l'image et la base de l'API, et sa défaillance se traduit par une absence de messages émis par le bot, elle-même détectée par la sonde de heartbeat.

---

## 2. Architecture retenue

```
                    ┌─────────────────────────────┐
                    │       Uptime Kuma           │
                    │  (conteneur sbl-uptime-kuma)│
                    └──────────────┬──────────────┘
                                   │
        ┌──────────────┬───────────┼───────────┬──────────────┐
        │ pull         │ pull      │ pull      │ pull         │ push
        ▼              ▼           ▼           ▼              ▲
   ┌─────────┐   ┌──────────┐  ┌────────┐  ┌────────┐   ┌──────────┐
   │ Frontend│   │ API      │  │Postgres│  │ Docker │   │   Bot    │
   │  HTTPS  │   │/api/health│ │  5432  │  │ socket │   │ Discord  │
   └─────────┘   └──────────┘  └────────┘  └────────┘   └──────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │   Notifications Discord     │
                    │  #alertes-technique         │
                    └─────────────────────────────┘
```

Uptime Kuma a été retenu plutôt qu'un couple Prometheus/Grafana pour trois raisons tenant à la typologie du projet :

1. **Proportionnalité** — SBL est une application à trafic modéré hébergée sur un VPS unique. Prometheus impose un serveur de métriques, un système de règles d'alerte et un Grafana pour la visualisation, soit trois conteneurs supplémentaires pour un besoin qui se résume à « le service répond-il et dans quel délai ».
2. **Empreinte** — Uptime Kuma consomme environ 100 Mo de RAM contre plusieurs centaines pour la stack Prometheus, sur un VPS où les ressources sont partagées avec PostgreSQL et PHP-FPM.
3. **Status page native** — la publication d'une page d'état publique répond directement au besoin de transparence vis-à-vis du staff SBL, sans développement complémentaire.

Le placement réseau du conteneur est un choix délibéré : Uptime Kuma est raccordé aux trois réseaux du projet (`web`, `internal`, `bot-network`). Il sonde ainsi l'API **depuis le réseau interne**, ce qui mesure la santé réelle de l'application et non celle du reverse proxy, tout en restant joignable par le bot pour recevoir son heartbeat.

---

## 3. Sondes mises en place

### 3.1 Frontend — sonde HTTP avec mot-clé

| Paramètre | Valeur |
|---|---|
| Type | HTTP(s) — Keyword |
| URL | `https://<FRONTEND_DOMAIN>` |
| Mot-clé attendu | `SBL` |
| Intervalle | 60 s |
| Tentatives avant alerte | 3 |

**Finalité.** Un serveur Nginx qui a perdu ses fichiers statiques renvoie un code 200 sur une page vide. Une sonde qui se contente de vérifier le code HTTP validerait cette situation. La recherche d'un mot-clé dans le corps de la réponse garantit que la page servie est bien l'application et non une coquille vide.

### 3.2 API — sonde HTTP avec requête JSON

| Paramètre | Valeur |
|---|---|
| Type | HTTP(s) — Json Query |
| URL | `http://api-nginx/api/health` (réseau interne) |
| Requête JSON | `$.status` |
| Valeur attendue | `ok` |
| Intervalle | 60 s |
| Tentatives avant alerte | 3 |

**Finalité.** C'est la sonde centrale du dispositif. L'endpoint `/api/health` (voir `api/src/Controller/HealthController.php`) ne se contente pas de confirmer que PHP-FPM répond : il vérifie la connectivité PostgreSQL, mesure sa latence, et compare les migrations Doctrine présentes sur le disque avec celles réellement exécutées en base.

Ce dernier contrôle couvre un cas de panne particulièrement pernicieux : un déploiement où le code est à jour mais où les migrations ont échoué. L'application démarre, répond aux requêtes, puis produit des erreurs SQL sur les seules fonctionnalités touchant les nouvelles colonnes. Sans cette sonde, l'anomalie n'est détectée qu'au premier utilisateur affecté.

L'endpoint renvoie un code HTTP 503 lorsqu'un contrôle critique échoue, ce qui permet une double détection (code HTTP et contenu JSON).

### 3.3 PostgreSQL — sonde de connexion native

| Paramètre | Valeur |
|---|---|
| Type | PostgreSQL |
| Chaîne de connexion | `postgres://<user>:<password>@postgres:5432/<db>` |
| Intervalle | 120 s |
| Tentatives avant alerte | 2 |

**Finalité.** La sonde API détecte déjà une base indisponible, mais elle ne permet pas de distinguer une panne applicative d'une panne de base de données. Cette sonde dédiée sert au **diagnostic différentiel** : si elle est au rouge en même temps que l'API, la cause est la base ; si elle est au vert, la cause est applicative. Ce distinguo fait gagner un temps considérable lors du traitement d'une anomalie.

L'intervalle est volontairement plus long (120 s) pour limiter le nombre de connexions ouvertes inutilement sur le pool PostgreSQL.

### 3.4 Bot Discord — sonde push (heartbeat)

| Paramètre | Valeur |
|---|---|
| Type | Push |
| Période de grâce | 120 s |
| Fréquence d'émission | 60 s |

**Finalité.** Le bot n'expose aucun port : il vit sur un réseau isolé et n'accepte aucune connexion entrante, par choix de sécurité. Il ne peut donc pas être sondé de l'extérieur. Le mécanisme est inversé : le bot appelle périodiquement une URL de push fournie par Uptime Kuma, et l'absence de signal pendant plus de 120 secondes (deux cycles manqués) déclenche l'alerte.

Ce que cette sonde apporte au-delà d'un simple contrôle de conteneur : le heartbeat n'est émis **que si la connexion websocket vers Discord est effectivement établie** (`client.isReady()`). Elle détecte donc le bot « zombie » — process Node vivant, conteneur au vert, mais websocket rompue et bot ne répondant plus à aucune commande. Une sonde de conteneur validerait cette situation ; le heartbeat la révèle.

L'implémentation transmet également la latence websocket, ce qui permet de suivre la qualité de la connexion Discord dans le temps. Voir `bot/monitoring/heartbeat.js`.

### 3.5 Certificat TLS

| Paramètre | Valeur |
|---|---|
| Type | Intégré à la sonde HTTP du frontend |
| Seuil d'alerte | 14 jours avant expiration |

**Finalité.** Les certificats Let's Encrypt sont renouvelés automatiquement par Traefik, mais ce renouvellement peut échouer silencieusement (challenge HTTP bloqué, quota atteint). L'échec n'a aucune conséquence visible jusqu'au jour de l'expiration, où l'ensemble des navigateurs bloque l'accès au site. Un préavis de 14 jours laisse largement le temps d'intervenir manuellement.

### 3.6 Conteneurs Docker

| Paramètre | Valeur |
|---|---|
| Type | Docker Container |
| Hôte | `/var/run/docker.sock` (montage en lecture seule) |
| Conteneurs | `sbl-api`, `sbl-postgres`, `sbl-frontend`, `sbl-bot` |
| Intervalle | 60 s |

**Finalité.** Les conteneurs sont configurés en `restart: unless-stopped`. Un conteneur qui plante et redémarre en boucle peut donc rester invisible : entre deux redémarrages, il répond normalement aux sondes HTTP. Cette sonde surveille l'état du conteneur lui-même et révèle les redémarrages répétés, symptôme classique d'une fuite mémoire ou d'une erreur de configuration.

**Périmètre effectif.** Le conteneur `sbl-scheduler` n'est pas supervisé : le service `scheduler` n'est pas publié sur la branche `main` du dépôt d'infrastructure et n'existe donc pas en production. L'inscrire dans la sonde produirait un état rouge permanent et un flux d'alertes ininterrompu — précisément la fatigue d'alerte que la section 4 cherche à éviter. Le scheduler reste couvert indirectement, comme indiqué en section 1 : sa défaillance se traduit par une absence de messages émis par le bot, détectée par la sonde de heartbeat. La ligne est à réintroduire dans `docs/scripts/setup-uptime-kuma.py` (`DOCKER_CONTAINERS`) le jour où le service est déployé.

---

## 4. Critères de qualité et de performance

Les seuils suivants ne sont pas des valeurs génériques : ils ont été calibrés sur les contraintes réelles du projet — un VPS unique, sans redondance, pour une ligue amateur dont l'activité se concentre sur les soirées de match.

| Indicateur | Cible | Seuil d'alerte | Justification |
|---|---|---|---|
| Disponibilité mensuelle (frontend) | ≥ 99 % | < 99 % | ≈ 7 h de coupure tolérée par mois. Un objectif à 99,9 % serait malhonnête sur une infrastructure sans redondance : une simple mise à jour du noyau du VPS le rendrait inatteignable. |
| Disponibilité mensuelle (API) | ≥ 99 % | < 99 % | Identique — l'API et le frontend partagent le même point de défaillance unique. |
| Temps de réponse `/api/health` | < 300 ms | > 1000 ms | La cible correspond au comportement nominal observé. Le seuil d'alerte, plus permissif, évite les faux positifs lors des pics d'activité en soirée de match. |
| Latence PostgreSQL | < 50 ms | > 200 ms | Seuil codé dans `HealthController::DB_LATENCY_WARNING_MS`, qui bascule le statut en `degraded`. |
| Latence websocket Discord | < 200 ms | > 500 ms | Au-delà, le délai de réponse des commandes du bot devient perceptible. |
| Migrations en attente | 0 | ≥ 1 | Tolérance nulle : signale systématiquement un déploiement incomplet. |
| Expiration certificat TLS | > 30 j | < 14 j | Préavis suffisant pour une intervention manuelle. |

**Distinction `degraded` / `down`.** L'endpoint de santé différencie trois états plutôt que deux. Un service `degraded` (latence base élevée, migration en attente) fonctionne encore : il ne justifie pas une alerte nocturne, mais doit être traité rapidement. Cette granularité évite la fatigue d'alerte, principal facteur d'échec d'un système de supervision — un dispositif qui alerte trop finit par être ignoré.

---

## 5. Modalité des signalements

### 5.1 Canal

Les notifications sont émises vers un **webhook Discord** pointant sur le canal `#alertes-technique` du serveur SBL. Ce choix découle du contexte du projet : le staff SBL et le développeur communiquent déjà exclusivement sur Discord. Un système d'alerte par e-mail aurait introduit un canal supplémentaire, consulté moins fréquemment, avec un risque réel de classement en indésirables.

### 5.2 Politique d'escalade

| Niveau | Déclencheur | Destinataire | Délai |
|---|---|---|---|
| Information | Bascule en `degraded` | `#alertes-technique` | Immédiat |
| Alerte | Sonde `down` après 3 tentatives | `#alertes-technique` + mention du développeur | ≈ 3 min après l'incident |
| Escalade | Indisponibilité continue > 15 min | Mention du staff SBL | 15 min |

L'escalade vers le staff n'est déclenchée qu'au-delà de 15 minutes. En deçà, une coupure passe généralement inaperçue des utilisateurs et une notification au client génèrerait une inquiétude disproportionnée. Ce paramétrage traduit une règle simple : **on n'alerte le client que sur ce qu'il constaterait de lui-même.**

### 5.3 Anti-faux-positifs

Trois mesures limitent le bruit :

- **3 tentatives avant alerte** — un timeout réseau isolé ne déclenche rien.
- **Intervalle de 60 s** — soit environ 3 minutes entre l'incident réel et la notification, un compromis acceptable pour ce type de service.
- **Notification de résolution** — Uptime Kuma signale également le retour à la normale, ce qui permet de distinguer un incident transitoire d'une panne durable sans consulter le tableau de bord.

### 5.4 Status page publique

Une page d'état publique est exposée sur `https://<MONITORING_DOMAIN>/status/sbl`. Elle affiche la disponibilité des services sur 90 jours et l'historique des incidents. Elle sert deux objectifs : permettre au staff SBL de vérifier lui-même si un problème est global ou local à son poste, et documenter la fiabilité du service dans la durée.

---

## 6. Mise en œuvre

### 6.1 Variables d'environnement

```dotenv
MONITORING_DOMAIN=status.exemple.fr
UPTIME_KUMA_PUSH_URL=http://uptime-kuma:3001/api/push/<TOKEN>
UPTIME_KUMA_PUSH_INTERVAL=60
```

Le token de push est généré par Uptime Kuma à la création de la sonde de type *Push*.

### 6.2 Démarrage

```bash
docker compose up -d uptime-kuma
```

Puis, à la première connexion sur `https://<MONITORING_DOMAIN>`, créer le compte
administrateur — l'interface n'est pas exposée sans authentification.

La configuration du dispositif est ensuite automatisée par
`docs/scripts/setup-uptime-kuma.py`, qui pilote l'API socket.io d'Uptime Kuma.
Le script est idempotent : il peut être relancé sans dupliquer les sondes.

```bash
docker run --rm --network sbl_web \
  -e KUMA_URL=http://uptime-kuma:3001 \
  -e KUMA_USERNAME -e KUMA_PASSWORD -e DISCORD_WEBHOOK_URL \
  -v /opt/sbl/.env:/opt/sbl/.env:ro \
  sbl-kuma-setup:1
```

Il effectue les étapes suivantes, décrites ici pour mémoire — et à suivre
manuellement dans l'interface si le script est indisponible :


1. Créer le compte administrateur (l'interface n'est pas exposée sans authentification).
2. Créer la notification Discord : *Settings → Notifications → Discord*, coller l'URL du webhook.
3. Créer les six sondes décrites en section 3, en rattachant la notification à chacune.
4. Récupérer le token de la sonde *Push*, le reporter dans `UPTIME_KUMA_PUSH_URL`, puis redémarrer le bot :
   ```bash
   docker compose up -d bot
   ```
5. Créer la status page publique : *Status Pages → New Status Page*, y ajouter les sondes frontend, API et bot.

### 6.3 Vérification du dispositif

Un système de supervision non testé est une hypothèse, pas une garantie. La chaîne complète se valide en provoquant une panne réelle :

```bash
# Provoquer l'incident
docker compose stop api

# Attendre ~3 min : l'alerte doit apparaître dans #alertes-technique

# Rétablir
docker compose start api

# La notification de résolution doit suivre sous 1 min
```

Ce test est à rejouer après toute modification du dispositif d'alerte.
