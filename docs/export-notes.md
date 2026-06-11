# Export du devis — notes préparatoires

> ⚠️ **Note historique (T1, rédigée avant la résolution d'OQ-1).** Depuis la spec v1.0.0,
> OQ-1 est résolue : export **texte brut** via `format_quote` (PDF = phase 2). Le contenu
> ci-dessous reflète l'état au moment de la rédaction, conservé pour l'audit trail.

La spec export-devis (v0.9.0) est validée mais **OQ-1 reste ouverte** : le format
contractuel d'export (PDF, CSV, ou les deux) n'est pas tranché par le métier.
Tant qu'OQ-1 n'est pas résolue, le module export (BHV-1, EVAL-1) est bloqué.

Options : **PDF** (document contractuel lisible, remis au client) ou **CSV**
(données structurées, réutilisables dans un tableur ou un SI tiers).
Critères de décision pour le sponsor : usage client visé (lecture vs retraitement),
valeur contractuelle attendue, coût d'implémentation et de maintenance.
Quel que soit le format, la mention « estimation » est requise (INV-1).
