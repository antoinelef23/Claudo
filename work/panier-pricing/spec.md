---
artifact: spec
feature: panier-pricing
version: 1.0.0
status: validated
owner: Antoine (test E2E — produit complexe)
validated_by: métier simulé — 2026-06-15
---

# Spec — Moteur de tarification de panier (checkout)

> **Le QUOI. Le contrat du métier.** Calcule le prix final d'un panier e-commerce :
> sous-total des lignes, remises par paliers de quantité, application des coupons (avec
> règles de cumul), frais de port (avec franco), puis TVA. Le résultat est une **ventilation
> de prix** (price breakdown) qui doit toujours se réconcilier au centime près.
> Périmètre **pur et déterministe** : tout en mémoire, montants en **centimes entiers**,
> le temps est une **donnée d'entrée** (`current_day`, jamais `now()`), aucune I/O.

## 1. Intent

Aux caisses (web), un écart d'un centime entre la ventilation affichée (sous-total, remises,
port, TVA) et le total débité est un incident comptable et une rupture de confiance. Cette
feature fournit le cœur de calcul qui **garantit la réconciliation exacte** du total à partir
de ses composantes, applique les remises et coupons selon des règles **déterministes et
ordonnées**, et ne produit **jamais** de total négatif ni de montant fractionnaire.

**KPI cible :** 0 écart de réconciliation (aujourd'hui : tickets SAV récurrents « le total ne
correspond pas au détail »).

## 2. Glossary

| Terme métier (FR) | Nom canonique (code) | Définition |
|---|---|---|
| Ligne de panier | `line` | `{sku, qty, unit_price_cents}` — un produit et sa quantité |
| Centime | `cents` | Unité monétaire **entière**. Aucun montant n'est un flottant. |
| Point de base | `bps` | 1 % = 100 bps. Tous les taux (remise, TVA) sont en bps entiers. |
| Remise palier | `tier_discount` | Remise **par ligne** fonction de la quantité (volume) |
| Coupon | `coupon` | Promotion niveau panier : `PERCENT`, `FIXED`, ou `FREE_SHIPPING` |
| Cumul | `stacking` | Règle qui décide quels coupons s'appliquent ensemble |
| Franco de port | `free_shipping_threshold` | Seuil de marchandise au-delà duquel le port est offert |
| Ventilation | `breakdown` | Décomposition `goods_subtotal / line_discounts / coupon_discounts / goods_final / shipping / tax / total` |
| Réconciliation | `reconciliation` | `total == goods_final + shipping + tax`, exact au centime |

## 3. Inputs / Output (contrat d'appel)

Fonction unique : `price(cart, coupons, context) -> breakdown`.

- `cart = {"lines": [{"sku": str, "qty": int, "unit_price_cents": int}, ...]}`
- `coupons = [{"code": str, "type": "PERCENT"|"FIXED"|"FREE_SHIPPING", "value": int,
  "stackable": bool, "priority": int, "valid_from": int, "valid_to": int}, ...]`
  — `value` est en **bps** pour `PERCENT`, en **cents** pour `FIXED`, ignoré pour `FREE_SHIPPING`.
  `valid_from`/`valid_to` sont des **indices de jour entiers** (bornes incluses).
- `context = {"shipping_cents": int, "free_shipping_threshold_cents": int,
  "tax_bps": int, "current_day": int}`
- **Sortie** `breakdown` (toutes valeurs entières sauf `applied_coupons`) :
  `{"goods_subtotal": int, "line_discounts": int, "coupon_discounts": int,
  "goods_final": int, "shipping": int, "tax": int, "total": int, "applied_coupons": [str]}`

## 4. Barème des paliers de quantité (donnée du contrat)

Par ligne, en fonction de `qty` (le palier le plus élevé atteint s'applique) :

| Condition | Taux de remise ligne |
|---|---|
| `qty >= 50` | 1000 bps (10 %) |
| `qty >= 20` | 500 bps (5 %) |
| sinon | 0 |

## 5. Invariants

- **INV-1 — Entiers stricts.** Tous les montants de la ventilation sont des `int` (centimes).
  Aucun flottant ne sort de `price`.
- **INV-2 — Jamais négatif.** `total >= 0`, `goods_final >= 0`. Aucune remise ne rend un
  montant négatif.
- **INV-3 — Réconciliation exacte.** `total == goods_final + shipping + tax`, au centime près,
  pour TOUT panier.
- **INV-4 — Plafond de remise.** `line_discounts + coupon_discounts <= goods_subtotal`.
  On ne remise jamais plus que la marchandise.
- **INV-5 — Déterminisme & ordre canonique.** Le calcul suit l'ordre **figé** : remises de
  ligne → coupons → port → TVA. Le résultat ne dépend **pas** de l'ordre du tableau `coupons`
  en entrée (tri canonique interne). Même entrée → même sortie, sans `now()` ni aléa.
- **INV-6 — Idempotence des coupons.** Deux coupons de même `code` dans l'entrée comptent comme
  un seul (dédoublonnage par `code`).
- **INV-7 — Arrondi maîtrisé.** La TVA est arrondie **au centime supérieur à la moitié**
  (*half-up* : `0.5` centime arrondit à `1`), arrondie **une seule fois** sur la base taxable
  totale (pas de double arrondi par ligne).

## 6. Behaviors

### BHV-1 — Panier vide
- **Given** `cart.lines == []`
- **Then** ventilation toute à zéro, `total == 0`, `applied_coupons == []`, aucune erreur.
  Aucun port n'est facturé sur un panier sans marchandise.

### BHV-2 — Ligne simple, sans promotion
- **Given** une ligne `qty < 20`, aucun coupon
- **Then** `goods_subtotal == qty * unit_price_cents`, `line_discounts == 0`,
  `goods_final == goods_subtotal`, puis port + TVA selon `context`.

### BHV-3 — Remise par palier de quantité
- **Given** une ligne dont `qty` atteint un palier (§4)
- **Then** `line_discounts == floor(line_gross * taux_bps / 10000)` (arrondi **vers le bas**),
  `goods_final` diminué d'autant.
- **Edge cases :**
  - **BHV-3a** — `qty == 20` exactement : palier 5 % **inclus**.
  - **BHV-3b** — `qty == 50` exactement : palier 10 % **inclus**.

### BHV-4 — Coupon PERCENT
- **Given** un coupon `PERCENT` valide et cumulable
- **Then** `coupon_discounts += floor(goods_courants * value_bps / 10000)` appliqué sur la
  marchandise **après** remises de ligne.

### BHV-5 — Coupon FIXED plafonné
- **Given** un coupon `FIXED` dont `value` dépasse la marchandise restante
- **Then** la remise est **plafonnée** à la marchandise restante : `goods_final` ne descend pas
  sous 0 (INV-2/INV-4). Le port et la TVA restent dus.

### BHV-6 — Cumul des coupons
- **Given** plusieurs coupons valides
- **Then** règle de cumul **déterministe** :
  - **BHV-6a** — tous `stackable: true` : ils s'appliquent **tous**, dans l'ordre canonique
    (`priority` croissant, puis `code` alphabétique), chacun sur la marchandise courante.
  - **BHV-6b** — au moins un coupon `stackable: false` (exclusif) présent et valide : on
    n'applique **qu'un seul** coupon — celui qui produit la **plus grosse remise** parmi tous
    les coupons valides (égalité tranchée par `priority` le plus bas, puis `code`).

### BHV-7 — Port et franco
- **Given** marchandise finale `goods_final`
- **Then** `shipping == 0` si `goods_final >= free_shipping_threshold_cents` **ou** si un coupon
  `FREE_SHIPPING` valide est appliqué ; sinon `shipping == context.shipping_cents`.
- **Edge case :** **BHV-7a** — `goods_final == free_shipping_threshold_cents` exactement : port
  offert (seuil **inclus**).

### BHV-8 — Coupon expiré ou pas encore valide
- **Given** un coupon dont `current_day < valid_from` ou `current_day > valid_to`
- **Then** il est **ignoré** (jamais appliqué, jamais dans `applied_coupons`).

### BHV-9 — Coupons dupliqués
- **Given** deux entrées de coupon partageant le même `code`
- **Then** elles comptent pour **une seule** (INV-6) ; `applied_coupons` ne liste un `code`
  qu'une fois.

### BHV-10 — TVA après remises
- **Given** la marchandise finale et le port
- **Then** `tax == round_half_up(taxable_base * tax_bps / 10000)` avec
  `taxable_base == goods_final + shipping` (la TVA porte aussi sur le port), arrondi half-up
  une seule fois (INV-7).

### BHV-11 — Total
- **Then** `total == goods_final + shipping + tax` (INV-3).

## 7. Examples

> Contexte par défaut sauf mention : `shipping_cents=500`, `free_shipping_threshold_cents=5000`,
> `tax_bps=2000` (20 %), `current_day=10`. Montants en centimes.

### EX-1 — panier vide
```yaml
input: { cart: {lines: []}, coupons: [] }
expected_output: { goods_subtotal: 0, line_discounts: 0, coupon_discounts: 0, goods_final: 0, shipping: 0, tax: 0, total: 0, applied_coupons: [] }
covers: [BHV-1]
```

### EX-2 — ligne simple sans promo
```yaml
input: { cart: {lines: [{sku: "A", qty: 2, unit_price_cents: 1000}]}, coupons: [] }
# goods 2000 ; port 500 (2000<5000) ; taxable 2500 ; TVA 500 ; total 3000
expected_output: { goods_subtotal: 2000, line_discounts: 0, coupon_discounts: 0, goods_final: 2000, shipping: 500, tax: 500, total: 3000, applied_coupons: [] }
covers: [BHV-2, BHV-10, BHV-11]
```

### EX-3 — palier 5 % à qty=20 (inclus)
```yaml
input: { cart: {lines: [{sku: "A", qty: 20, unit_price_cents: 1000}]}, coupons: [] }
# goods 20000 ; remise ligne 1000 (5%) ; goods_final 19000 ; franco (>=5000) port 0 ; TVA 3800
expected_output: { goods_subtotal: 20000, line_discounts: 1000, coupon_discounts: 0, goods_final: 19000, shipping: 0, tax: 3800, total: 22800, applied_coupons: [] }
covers: [BHV-3, BHV-3a, BHV-7]
```

### EX-4 — palier 10 % à qty=50 (inclus)
```yaml
input: { cart: {lines: [{sku: "A", qty: 50, unit_price_cents: 1000}]}, coupons: [] }
# goods 50000 ; remise ligne 5000 (10%) ; goods_final 45000 ; franco ; TVA 9000
expected_output: { goods_subtotal: 50000, line_discounts: 5000, coupon_discounts: 0, goods_final: 45000, shipping: 0, tax: 9000, total: 54000, applied_coupons: [] }
covers: [BHV-3b, BHV-7]
```

### EX-5 — coupon PERCENT cumulable
```yaml
input:
  cart: {lines: [{sku: "A", qty: 2, unit_price_cents: 1000}]}
  coupons: [{code: "WELCOME10", type: "PERCENT", value: 1000, stackable: true, priority: 10, valid_from: 0, valid_to: 100}]
# goods 2000 ; coupon 10% = 200 ; goods_final 1800 ; port 500 ; taxable 2300 ; TVA 460 ; total 2760
expected_output: { goods_subtotal: 2000, line_discounts: 0, coupon_discounts: 200, goods_final: 1800, shipping: 500, tax: 460, total: 2760, applied_coupons: ["WELCOME10"] }
covers: [BHV-4]
```

### EX-6 — coupon FIXED plafonné (total > 0 malgré marchandise à 0)
```yaml
input:
  cart: {lines: [{sku: "A", qty: 1, unit_price_cents: 500}]}
  coupons: [{code: "BIG", type: "FIXED", value: 99999, stackable: true, priority: 5, valid_from: 0, valid_to: 100}]
# goods 500 ; FIXED plafonné à 500 ; goods_final 0 ; port 500 ; taxable 500 ; TVA 100 ; total 600
expected_output: { goods_subtotal: 500, line_discounts: 0, coupon_discounts: 500, goods_final: 0, shipping: 500, tax: 100, total: 600, applied_coupons: ["BIG"] }
covers: [BHV-5, BHV-11]
```

### EX-7 — coupon exclusif bat le cumulable (meilleure remise unique)
```yaml
input:
  cart: {lines: [{sku: "A", qty: 2, unit_price_cents: 5000}]}
  coupons:
    - {code: "STACK5",  type: "PERCENT", value: 500,  stackable: true,  priority: 10, valid_from: 0, valid_to: 100}
    - {code: "EXCL20",  type: "PERCENT", value: 2000, stackable: false, priority: 20, valid_from: 0, valid_to: 100}
# goods 10000 ; exclusif présent -> meilleur coupon unique : EXCL20 (2000) > STACK5 (500) ; goods_final 8000 ; franco ; TVA 1600
expected_output: { goods_subtotal: 10000, line_discounts: 0, coupon_discounts: 2000, goods_final: 8000, shipping: 0, tax: 1600, total: 9600, applied_coupons: ["EXCL20"] }
covers: [BHV-6, BHV-6b]
```

### EX-8 — coupon expiré ignoré
```yaml
input:
  cart: {lines: [{sku: "A", qty: 1, unit_price_cents: 1000}]}
  coupons: [{code: "OLD", type: "PERCENT", value: 5000, stackable: true, priority: 1, valid_from: 0, valid_to: 5}]
# current_day 10 > valid_to 5 -> ignoré ; goods 1000 ; port 500 ; taxable 1500 ; TVA 300 ; total 1800
expected_output: { goods_subtotal: 1000, line_discounts: 0, coupon_discounts: 0, goods_final: 1000, shipping: 500, tax: 300, total: 1800, applied_coupons: [] }
covers: [BHV-8]
```

## 8. Evals — merge gate

*Convention : test pytest `@pytest.mark.eval`, nom contenant l'ID en minuscules (ex. `test_eval_1_...`).*

| ID | Type | Description | Couvre | Seuil |
|---|---|---|---|---|
| EVAL-1 | deterministic | EX-1 à EX-8 vérifiés **exactement** (toutes clés de la ventilation) | BHV-1..BHV-11 | 100 % |
| EVAL-2 | property-based | sur **1000 paniers** aléatoires (seed fixe) : INV-1 (tout entier), INV-2 (`total>=0`, `goods_final>=0`), INV-3 (réconciliation exacte), INV-4 (remise totale ≤ goods_subtotal) tiennent toujours | INV-1, INV-2, INV-3, INV-4 | 100 % |
| EVAL-3 | deterministic | **déterminisme & idempotence** : (a) deux appels identiques → ventilation identique ; (b) permuter l'ordre du tableau `coupons` → même résultat (INV-5) ; (c) dupliquer un coupon → même résultat qu'une occurrence (INV-6) | INV-5, INV-6, BHV-9 | 100 % |
| EVAL-4 | deterministic | **arrondi half-up** : un cas dont la TVA tombe sur `x.5` centime arrondit à `x+1` ; aucun double arrondi (la TVA d'un panier multi-lignes == TVA calculée une fois sur la base totale) | INV-7, BHV-10 | 100 % |

## 9. Non-goals

- **NG-1** — Persistance / base de données : le calcul est pur, en mémoire.
- **NG-2** — Multi-devises / taux de change : un seul taux de TVA passé en entrée, montants en cents.
- **NG-3** — Catalogue réel / référentiel produit : `unit_price_cents` est une donnée d'entrée.
- **NG-4** — Dates calendaires / fuseaux : la validité des coupons est un **indice de jour entier**.
- **NG-5** — Remises par catégorie ou « 3 achetés = 1 offert » : hors scope (seulement paliers de quantité §4 + coupons §6).

## 10. Open questions

*(aucune — spec close pour le test E2E)*

## 11. Changelog

| Version | Date | Auteur | Changement |
|---|---|---|---|
| 1.0.0 | 2026-06-15 | métier (simulé E2E) | Création — contrat v1 du moteur de tarification |
