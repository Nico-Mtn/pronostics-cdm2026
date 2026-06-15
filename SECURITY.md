# Politique de sécurité — Pronostix

## Signaler une vulnérabilité

Si vous découvrez une faille de sécurité dans ce projet, merci de la signaler de
manière responsable :

- **Ouvrez un [Security Advisory privé](https://github.com/Nico-Mtn/pronostics-cdm2026/security/advisories/new)** sur ce dépôt (méthode privilégiée), ou
- **Ouvrez une issue** en restant vague sur les détails techniques sensibles, et indiquez qu'il s'agit d'un sujet de sécurité.

Merci de **ne pas divulguer publiquement** les détails d'une vulnérabilité avant
qu'un correctif n'ait été déployé.

Délai de réponse visé : **sous 7 jours**.

## Périmètre

Ce projet est un site statique de pronostics sportifs, hébergé sur GitHub Pages.
Il **ne collecte aucune donnée personnelle** et **ne demande aucune authentification**
aux visiteurs. Les seules données traitées sont :

- les scores publics récupérés via l'API [football-data.org](https://www.football-data.org/) ;
- pour les utilisateurs qui l'activent **explicitement** sur mobile : un abonnement
  aux notifications push (Web Push), stocké de façon anonyme (aucun email, aucun
  identifiant personnel — uniquement le *endpoint* technique du navigateur).

Sont notamment dans le périmètre :

- exposition de secrets dans le code livré (clé API, clés VAPID privées, tokens) ;
- détournement du service d'abonnement push (Cloudflare Worker) ;
- injection de contenu dans la page générée.

## Bonnes pratiques appliquées

- Aucune clé secrète n'est stockée dans le dépôt : la clé API et les clés VAPID
  sont des **secrets GitHub Actions** ; le token GitHub et les secrets du Worker
  sont des **secrets Cloudflare** chiffrés.
- La clé **publique** VAPID est la seule valeur sensible présente côté client,
  ce qui est conforme au protocole Web Push.
- Les endpoints d'administration du Worker (`/list`, `/remove`) sont protégés par
  un secret partagé.

## Hors périmètre

- Les vulnérabilités propres aux plateformes tierces (GitHub Pages, Cloudflare,
  football-data.org) doivent être signalées directement à ces fournisseurs.
- L'indisponibilité temporaire liée aux quotas gratuits de ces services.
