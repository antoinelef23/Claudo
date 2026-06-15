---
artifact: spec
feature: agent-douche
version: 1.0.0
status: draft # → validated après Vibe Workshop avec le métier
owner: <Owner>
validated_by: <métier — à signer en clôture du Vibe Workshop>
---

# Spec — Agent Douche (configurateur salle de bain)

> ⚠️ **Exemple illustratif.** Les valeurs chiffrées et les exemples sont des hypothèses à confirmer
> en Vibe Workshop avec le métier.

## 1. Intent

Un client dépose une photo de sa salle de bain ; l'agent lui propose 3 ambiances (moderne, naturel, classique) reconstituées avec des produits réels du catalogue produits, puis l'emmène jusqu'au panier avec les services associés (livraison, pose, devis). On supprime la friction entre l'inspiration et l'achat.

**KPI cible :** taux de conversion photo → panier ≥ 8 % ; panier moyen du tunnel ≥ 1,5× le panier moyen rayon salle de bain. Horizon : échéance projet cible.

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Ambiance | `ambiance` | Univers décoratif généré : exactement un parmi `moderne`, `naturel`, `classique` |
| Photo client | `room_photo` | Image de la salle de bain existante déposée par le client (JPEG/PNG/HEIC, ≤ 15 Mo) |
| Produit matché | `matched_product` | Référence active du catalogue produits retenue pour une ambiance |
| Rendu | `render` | Visualisation de la salle de bain du client recomposée dans une ambiance |
| Tunnel | `checkout_flow` | Parcours panier + services (livraison, pose, devis) |

## 3. Invariants

- **INV-1** — Tout produit affiché MUST exister au catalogue produits, être actif et disponible (stock ou délai affiché). Jamais de produit halluciné.
- **INV-2** — Chaque rendu MUST proposer exactement 3 ambiances : `moderne`, `naturel`, `classique`.
- **INV-3** — Le prix affiché MUST être le prix catalogue temps réel au moment de l'affichage ; tout écart au panier est recalculé.
- **INV-4** — La photo client MUST NOT être conservée au-delà de la session sans consentement explicite (RGPD) et MUST NOT servir à l'entraînement de modèles.
- **INV-5** — Le système MUST NOT produire de devis ferme : le devis pose est une estimation, marquée comme telle, transmise au réseau de pose pour validation.
- **INV-6** — Si la photo ne contient pas de salle de bain identifiable, le système MUST le dire et redemander — jamais de génération à l'aveugle.

## 4. Behaviors

### BHV-1 — Dépôt de la photo
- **Given** un client sur le configurateur, sans compte requis
- **When** il dépose une photo (JPEG/PNG/HEIC ≤ 15 Mo)
- **Then** le système détecte la pièce, ses éléments (douche/baignoire, vasque, sol, murs, fenêtre) et affiche un récapitulatif « voici ce que j'ai compris » en ≤ 10 s (p95)
- **Edge cases :**
 - **BHV-1a** — photo floue/sombre : demande de reprise avec conseil de cadrage, max 3 tentatives
 - **BHV-1b** — pièce ≠ salle de bain : message explicite (INV-6)
 - **BHV-1c** — personnes visibles sur la photo : visages floutés avant tout traitement

### BHV-2 — Proposition des 3 ambiances
- **Given** une photo analysée avec succès
- **When** le client demande les propositions
- **Then** 3 rendus (un par ambiance, INV-2) s'affichent en ≤ 30 s (p95), chacun respectant la géométrie de la pièce (emplacements eau/évacuations inchangés)

### BHV-3 — Produits matchés
- **Given** une ambiance sélectionnée
- **When** le client ouvre le détail
- **Then** la liste des produits du rendu s'affiche : référence, prix temps réel, dispo, lien fiche produit ; chaque élément visuel majeur du rendu correspond à un produit (INV-1)
- **Edge cases :**
 - **BHV-3a** — produit devenu indisponible : substitution par l'équivalent le plus proche, badge « remplacé »

### BHV-4 — Panier + services
- **Given** une sélection de produits dans une ambiance
- **When** le client valide
- **Then** le panier est créé avec les produits, et les services proposés : livraison (créneaux réels), pose (estimation, INV-5), prise de RDV devis

## 5. Examples

### EX-1 — cas nominal
```yaml
input:
 room_photo: "sdb_6m2_baignoire_carrelage_blanc.jpg" # 6 m², baignoire, fenêtre nord
 action: "proposer les ambiances"
expected_output:
 renders: 3
 ambiances: [moderne, naturel, classique]
 naturel:
 produits_exemple:
 - { ref: "vasque à poser bambou", prix: "catalogue temps réel", dispo: true }
 - { ref: "receveur 120x90 effet pierre", prix: "catalogue temps réel", dispo: true }
 geometrie: "baignoire remplacée par douche au même emplacement d'évacuation"
covers: [BHV-2, BHV-3, INV-1, INV-2]
```

### EX-2 — photo hors sujet
```yaml
input:
 room_photo: "salon_canape.jpg"
expected_output:
 message: "Je ne reconnais pas de salle de bain sur cette photo — pouvez-vous photographier la pièce à rénover ?"
 renders: 0
covers: [BHV-1b, INV-6]
```

### EX-3 — produit indisponible entre rendu et panier
```yaml
input:
 action: "ajouter au panier"
 produit: { ref: "carrelage X", statut_stock: "rupture nationale" }
expected_output:
 panier: "créé avec substitut équivalent (même gamme de prix ±10 %), badge 'remplacé'"
covers: [BHV-3a, INV-1, INV-3]
```

## 6. Non-goals

- **NG-1** — Pas de plan technique / plomberie : on ne déplace pas les arrivées d'eau (réduit le risque, géré par le service pose).
- **NG-2** — Pas de paiement dans le configurateur : on alimente le panier existant (critère « risque maîtrisé » du lab).
- **NG-3** — Pas d'autres pièces que la salle de bain en V1.
- **NG-4** — Pas de compte requis avant le panier.

## 7. Evals — merge gate

| ID | Type | Description | Couvre | Seuil de succès |
|---|---|---|---|---|
| EVAL-1 | deterministic | Toute réf produit retournée existe et est active dans le catalogue (jeu de 200 rendus) | INV-1, BHV-3 | 100 % |
| EVAL-2 | deterministic | 3 ambiances exactement, nommage conforme, sur 50 photos de test | INV-2, BHV-2 | 100 % |
| EVAL-3 | llm-judge | Cohérence rendu ↔ ambiance ↔ géométrie de la pièce (rubrique en annexe) | BHV-2 | ≥ 8/10 sur 50 cas |
| EVAL-4 | deterministic | Photos hors sujet (30 images pièges) → refus explicite, 0 rendu | INV-6, BHV-1b | 100 % |
| EVAL-5 | property-based | Prix panier = somme prix catalogue temps réel, sur paniers générés | INV-3 | 100 % |
| EVAL-6 | deterministic | Latence p95 : analyse ≤ 10 s, rendus ≤ 30 s (banc de 100 photos) | BHV-1, BHV-2 | p95 sous seuil |

## 8. Open questions

- **OQ-1** — Quel périmètre catalogue exact J1 (rayon sanitaire complet ? carrelage ?) → bloque BHV-3.
- **OQ-2** — Le service pose est-il disponible sur toute la France ou par zone ? → impacte BHV-4.
- **OQ-3** — Génération des rendus : contrainte de marque sur les images (mention « image générée ») ?

## 9. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | <date Vibe Workshop> | Vibe Workshop (PE + métier) | Création — exemple pré-rempli à valider |
