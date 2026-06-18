---
artifact: spec
feature: agent-douche
version: 1.0.1
status: draft            # → validated after the Vibe Workshop with the client's business team
owner: <Owner the client>
validated_by: <the client's business team — to be signed off at the close of the Vibe Workshop>
---

# Spec — Agent Douche (bathroom configurator)

> ⚠️ **Illustrative example.** The numeric values and the examples are assumptions to be confirmed
> in a Vibe Workshop with the client's business team. Deadline: projects fair mid-October 2026.

## 1. Intent

A customer uploads a photo of their bathroom; the agent proposes 3 moods (modern, natural, classic) reconstructed with real products from the client catalog, then takes them all the way to the cart with the associated services (delivery, installation, quote). We remove the friction between inspiration and purchase.

**Target KPI:** photo → cart conversion rate ≥ 8%; average cart of the funnel ≥ 1.5× the average cart of the bathroom department. Horizon: projects fair mid-October.

## 2. Glossary

| Business term (EN) | Canonical name (code) | Definition |
|---|---|---|
| Mood | `ambiance` | Generated decorative theme: exactly one of `moderne`, `naturel`, `classique` |
| Customer photo | `room_photo` | Image of the existing bathroom uploaded by the customer (JPEG/PNG/HEIC, ≤ 15 MB) |
| Matched product | `matched_product` | Active reference from the client catalog selected for a mood |
| Render | `render` | Visualization of the customer's bathroom recomposed in a mood |
| Funnel | `checkout_flow` | Cart + services journey (delivery, installation, quote) |

## 3. Invariants

- **INV-1** — Every displayed product MUST exist in the client catalog, be active and available (in stock or with a displayed lead time). Never a hallucinated product.
- **INV-2** — Each render MUST propose exactly 3 moods: `moderne`, `naturel`, `classique`.
- **INV-3** — The displayed price MUST be the real-time catalog price at the moment of display; any discrepancy at the cart is recomputed.
- **INV-4** — The customer photo MUST NOT be kept beyond the session without explicit consent (GDPR) and MUST NOT be used for model training.
- **INV-5** — The system MUST NOT produce a firm quote: the installation quote is an estimate, marked as such, forwarded to the installation network for validation.
- **INV-6** — If the photo does not contain an identifiable bathroom, the system MUST say so and ask again — never blind generation.

## 4. Behaviors

### BHV-1 — Photo upload
- **Given** a customer on the configurator, with no account required
- **When** they upload a photo (JPEG/PNG/HEIC ≤ 15 MB)
- **Then** the system detects the room, its elements (shower/bathtub, washbasin, floor, walls, window) and displays a "here is what I understood" summary within ≤ 10 s (p95)
- **Edge cases:**
  - **BHV-1a** — blurry/dark photo: request to retake with framing advice, max 3 attempts
  - **BHV-1b** — room ≠ bathroom: explicit message (INV-6)
  - **BHV-1c** — people visible in the photo: faces blurred before any processing

### BHV-2 — Proposal of the 3 moods
- **Given** a successfully analyzed photo
- **When** the customer requests the proposals
- **Then** 3 renders (one per mood, INV-2) are displayed within ≤ 30 s (p95), each respecting the geometry of the room (water/drainage locations unchanged)

### BHV-3 — Matched products
- **Given** a selected mood
- **When** the customer opens the detail
- **Then** the list of the render's products is displayed: reference, real-time price, availability, product-page link; each major visual element of the render corresponds to a product (INV-1)
- **Edge cases:**
  - **BHV-3a** — product become unavailable: substitution with the closest equivalent, "replaced" badge

### BHV-4 — Cart + services
- **Given** a selection of products in a mood
- **When** the customer confirms
- **Then** the client cart is created with the products, and the proposed services: delivery (real time slots), installation (estimate, INV-5), quote appointment booking

## 5. Examples

### EX-1 — nominal case
```yaml
input:
  room_photo: "sdb_6m2_baignoire_carrelage_blanc.jpg"   # 6 m², bathtub, north window
  action: "propose the moods"
expected_output:
  renders: 3
  ambiances: [moderne, naturel, classique]
  naturel:
    produits_exemple:
      - { ref: "bamboo countertop washbasin", prix: "real-time catalog", dispo: true }
      - { ref: "120x90 stone-effect shower tray", prix: "real-time catalog", dispo: true }
    geometrie: "bathtub replaced by a shower at the same drainage location"
covers: [BHV-2, BHV-3, INV-1, INV-2]
```

### EX-2 — off-topic photo
```yaml
input:
  room_photo: "salon_canape.jpg"
expected_output:
  message: "I do not recognize a bathroom in this photo — could you photograph the room to be renovated?"
  renders: 0
covers: [BHV-1b, INV-6]
```

### EX-3 — product unavailable between render and cart
```yaml
input:
  action: "add to cart"
  produit: { ref: "tile X", statut_stock: "national stockout" }
expected_output:
  panier: "created with an equivalent substitute (same price range ±10%), 'replaced' badge"
covers: [BHV-3a, INV-1, INV-3]
```

## 6. Non-goals

- **NG-1** — No technical / plumbing plan: we do not move the water inlets (reduces risk, handled by the installation service).
- **NG-2** — No payment in the configurator: we feed the existing client cart (the lab's "controlled risk" criterion).
- **NG-3** — No rooms other than the bathroom in V1.
- **NG-4** — No account required before the cart.

## 7. Evals — merge gate

| ID | Type | Description | Covers | Success threshold |
|---|---|---|---|---|
| EVAL-1 | deterministic | Every returned product ref exists and is active in the catalog (set of 200 renders) | INV-1, BHV-3 | 100% |
| EVAL-2 | deterministic | Exactly 3 moods, compliant naming, over 50 test photos | INV-2, BHV-2 | 100% |
| EVAL-3 | llm-judge | Consistency render ↔ mood ↔ room geometry (rubric in appendix) | BHV-2 | ≥ 8/10 over 50 cases |
| EVAL-4 | deterministic | Off-topic photos (30 trap images) → explicit refusal, 0 render | INV-6, BHV-1b | 100% |
| EVAL-5 | property-based | Cart price = sum of real-time catalog prices, over generated carts | INV-3 | 100% |
| EVAL-6 | deterministic | p95 latency: analysis ≤ 10 s, renders ≤ 30 s (bench of 100 photos) | BHV-1, BHV-2 | p95 under threshold |

## 8. Open questions

- **OQ-1** — What exact catalog scope on day 1 (full sanitary department? tiling?) → blocks BHV-3.
- **OQ-2** — Is the installation service available across all of France or by zone? → impacts BHV-4.
- **OQ-3** — Render generation: brand constraint on the images ("generated image" notice)?

## 9. Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | <Vibe Workshop date> | Vibe Workshop (PE + business) | Creation — SFEIR pre-filled example to validate |
| 1.0.1 | 2026-06-18 | translation | English translation (form only, no substance change) |
