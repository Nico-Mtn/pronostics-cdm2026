# Contribuer à Pronostix

Merci de l'intérêt que tu portes à **Pronostix** (« Prono de Nono ») ! 🎉

C'est un projet **personnel, gratuit, sans publicité et sans paris** : des pronostics
générés par un modèle statistique pour la Coupe du Monde 2026, publiés sous forme de
PWA sur GitHub Pages. Il est développé sur mon temps libre par **Nico-Mtn**.

Les contributions et les retours sont les bienvenus, dans la limite de ce qu'un projet
solo peut absorber. Voici comment aider au mieux.

## Signaler un bug ou proposer une idée

Le plus simple est d'**ouvrir une issue** :

- 🐛 **Bug** — utilise le modèle « Signaler un bug » (que vois-tu, qu'attendais-tu,
  sur quel match / quel écran, capture si possible).
- 💡 **Suggestion** — utilise le modèle « Proposer une amélioration » (le besoin, et
  éventuellement une piste de solution).

Merci de vérifier d'abord qu'une issue similaire n'existe pas déjà.

## Comment marche le projet (pour situer)

- L'app est un **site statique** : `template.html` (la page + le JS) et les données.
- `update.py` **génère `index.html`** en injectant les données (scores réels via
  football-data.org + pronostics du modèle) dans le template.
- Un **workflow GitHub Actions** (`.github/workflows/update.yml`) régénère et déploie
  la page sur GitHub Pages ; un **Cloudflare Worker** déclenche les mises à jour.
- La logique du modèle est décrite dans `MODELE.md`.

## Proposer du code (Pull Request)

Les PR sont possibles mais évaluées au cas par cas (c'est un projet perso) :

1. Ouvre d'abord une issue pour en discuter, surtout pour un changement non trivial.
2. Garde les changements **ciblés** et teste en local (`python update.py` régénère
   `index.html` — vérifie le rendu).
3. Respecte le style existant et **conserve le crédit** en en-tête des fichiers.

## Code de conduite

En participant, tu acceptes de respecter le [Code de conduite](CODE_OF_CONDUCT.md).
Sois bienveillant : on est là pour le plaisir du foot et de la data. ⚽

## Licence

En contribuant, tu acceptes que ta contribution soit publiée sous la licence
[MIT](LICENSE) du projet.
