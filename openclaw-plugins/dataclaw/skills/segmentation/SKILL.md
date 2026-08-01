---
name: segmentation
description: Segment a population into decision-serving groups inside the Dataclaw data-science workflow — pick the segmentation type from the decision, build a leakage-safe feature space, cluster by data shape, prove the segments are stable and separable rather than noise, then profile and operationalize them with a typing model. Use for customer, market, audience, account, patient, and HCP segmentation, RFM and value/CLV tiers, needs-based and attitudinal personas, behavioral and journey clustering, k-means / GMM / HDBSCAN / latent-class methods, mixed-type and high-dimensional segmentation, and uplift / persuadable targeting.
tags: [segmentation, clustering, targeting, method]
---

**Related skills:** `dataclaw_data_science` (governed data, notebook, plan, MLflow, review, and delivery workflow), `structured_eda` (feature-space EDA, cluster tendency, hypothesis/finding ledger, readiness), `feature_engineering` (leakage-safe feature space and the typing model's inputs), `survey_analytics` (attitudinal / needs batteries — it governs latent-class methods and weighting), `predictive_modeling` (value/risk tiers and the segment-assignment typing model), `causal_inference` and `experiment_design` (uplift / treatment-effect segmentation), `analysis_review` (validation gate), `visualization` (analysis-time charts), `report_design` (final report authorship), `artifacts` (publication and revision).

# Segmentation Playbook

Use when the goal is to divide a population into segments that serve a decision — customers, accounts, users, patients, HCPs, geographies. Segmentation runs inside the `dataclaw_data_science` workflow as notebook code and adds only the segmentation discipline below. There is no segmentation tool or plugin to call: the statistics run in the notebook with standard libraries (`scikit-learn` and `scipy` for clustering, linkage, and internal metrics; `hdbscan`, `kmodes`, and `gower` for density and mixed-type clustering; `prince` for MCA/FAMD; `stepmix` for latent class/profile models; `causalml`/`econml` and `scikit-uplift` for treatment-effect segmentation). Two failure modes dominate: believing clusters that are only noise, and segmenting on the wrong construct for the decision — clustering on value or outcome when the decision is about who *responds*, or discovering groups when a decision-relevant split already exists.

Follow this process:

1. Frame the decision first — the segmentation type follows from it, not the reverse. Fix the decision the segments serve (targeting, personalization, portfolio strategy, product/needs design, risk tiering), the unit (customer, account, HCP, patient, session, geo), whether new units must be assignable later (a typing model is then required), the number of segments the organization can actually operate on, and whether protected or sensitive attributes are in scope (a fairness constraint, not a feature). Decide up front which of three questions this is: *discovery* (what groups exist), *value/risk tiering* (who is valuable or at risk), or *responsiveness* (who changes behavior under an intervention) — three different methods.

2. Discover data and run EDA before proposing major work: list datasets with `dataclaw_data_list_datasets`, open a notebook with `dataclaw_open_notebook`, and load frames with `dataclaw_data.get_dataframe(...)`. Fetch `structured_eda`. If the data is survey or attitudinal batteries (Likert, multi-select, needs statements), fetch and defer to `survey_analytics` — it governs measurement level, latent-class/profile estimation, and weighting; this skill governs the non-survey cases and the cross-cutting validation and actionability discipline. Characterize the feature space: types (continuous, ordinal, nominal, counts, compositional), scale and skew, missingness, collinearity, and outliers. Test **cluster tendency** (a Hopkins statistic clearly off the ~0.5 random baseline toward the clustered pole — confirm which pole your implementation uses, since the two conventions invert around 0.5: the classic `ΣU/(ΣU+ΣW)` form runs to ~1 for clustered data while R's `clustertend` / some `pyclustertend` builds run to ~0 — or a visibly non-uniform ordered dissimilarity matrix) before assuming any structure exists. Record feature-space, scale, missingness, and tendency findings with `dataclaw_record_eda_finding`, and confirm readiness with `dataclaw_summarize_eda_readiness`.

3. Choose the segmentation type from the decision and data shape (routing below) *before* choosing an algorithm, and state it in the plan. Prefer a transparent a-priori or RFM split when a decision-relevant grouping already exists — do not cluster to rediscover a variable you already have.

4. Propose a plan with `dataclaw_propose_plan` before execution, and wait for approval. Include the segmentation type and why, the feature space and its construction, the standardization/encoding/dimensionality choices, the candidate algorithms, how the number of segments will be selected reconciling statistical and operational criteria, the stability and validation protocol, the fairness constraint, the assignment/typing plan, and the refusal conditions — decided now, not during execution. Report progress with `dataclaw_update_plan` after every step status change.

5. Build the feature space leakage-safely. Fetch `feature_engineering`. Audit direct identifiers and high-cardinality near-identifiers first: exclude names, email addresses, phone numbers, account/customer/patient ids, free-text identifiers, and join keys from the feature matrix and model-visible profiles; retain only a protected join key outside the matrix when assignments must be joined back. Standardize continuous features (robustly when skewed); encode and measure mixed types with a distance that respects type (Gower, k-prototypes, or FAMD), never one-hot categoricals into k-means; reduce dimensionality (PCA for continuous, MCA for categorical, FAMD for mixed) when distance concentration threatens. For value tiers or uplift, model inputs are fold-scoped — `feature_engineering` owns the leakage rules. Exclude protected attributes and audit their proxies before clustering.

6. Fit candidates and select — never trust a single run. Match the algorithm to the data shape (routing below), run multiple seeds, and select on internal validity *and* a stability criterion, not inertia alone. For model-based methods (GMM, LCA/LPA) select by BIC and entropy; for k-means/PAM by silhouette plus stability; for density (HDBSCAN) by min-cluster-size and the noise share. Log each configuration as an MLflow run with comparable metrics and the seed set so `dataclaw_query_mlflow_runs` can reconstruct the comparison.

7. Validate stability and separation (contract below). Bootstrap the solution and report per-cluster Jaccard; drop or merge any cluster below the stability floor. Confirm separation on held-out data and that the segments reproduce out-of-sample before profiling.

8. Profile and operationalize (actionability contract below). Profile segments on descriptors *not* used to build them, size each segment, name them from evidence, and build a lightweight typing/assignment model with `predictive_modeling` so new units can be classified from routinely available fields. A statistically clean solution that implies no different decision, or a segment too small to operate, is not a result.

9. Review and deliver. Segmentation that drives targeting, pricing, credit, or treatment is high-risk — before marking the step ready for validation, request review with `dataclaw_request_analysis_review` and inspect it with `dataclaw_get_review_gate`; the `analysis_review` gate fires before validation. Display cluster-tendency and stability diagnostics, the segment profiles, and sizes through `visualization`. Deliver through `report_design_report` and `report_publish`, then `publish_artifact`, handing over the method, stability evidence, segment sizes, the typing rule, and fairness caveats; let `report_design` own prose, layout, and HTML.

## Segmentation type by decision

| Decision / question | Segmentation type | What to use | Required caveat |
|---|---|---|---|
| A decision-relevant grouping already exists (tier, region, lifecycle) | A-priori / rule-based | Business rules, no model | Do not cluster to rediscover a known variable; confirm the split actually separates the outcome. |
| Rank customers by value or risk | Value / risk tiering | RFM quantiles; or predicted CLV/churn via `predictive_modeling`, then tier | Tier on the predicted quantity, not a noisy proxy; RFM is descriptive, not predictive. |
| Who will respond to an intervention | Uplift / treatment-effect | Causal forests / meta-learners via `causal_inference` + `experiment_design`; `causalml`/`econml` | This is causal — never target by outcome level; separate persuadables from sure-things and sleeping-dogs. |
| What natural behavioral groups exist | Behavioral clustering (discovery) | k-means / GMM / PAM / HDBSCAN by data shape (below) | Test cluster tendency first; segments must be stable, not merely present. |
| What needs or attitudes group the market | Needs / attitudinal | Latent class / profile analysis on batteries via `survey_analytics` | Defer to `survey_analytics`; do not k-means Likert items. |
| Explain who does X with transparent rules | Supervised tree segmentation | CART / decision tree on the outcome | Interpretable but unstable; prune and report holdout, not resubstitution. |
| Group journeys or sequences | Sequence / journey | State or sequence clustering (Markov, edit-distance) | Align on the event grain; do not cluster raw counts as if order did not matter. |

## Clustering method by data shape

| Data shape | Method | Required caveat |
|---|---|---|
| Continuous, standardized, roughly convex clusters | k-means / MiniBatchKMeans | Standardize first; centroids are means, so no categoricals; sensitive to outliers and init — run multiple seeds. |
| Overlapping or elliptical clusters, want soft membership | Gaussian mixture | Select by BIC; it assumes Gaussian components with a covariance structure you must justify. |
| Mixed continuous + categorical | Gower + PAM/hierarchical, k-prototypes, or FAMD→cluster (`gower`, `kmodes`, `prince`) | Never one-hot into k-means; the distance must respect variable type. |
| Categorical / ordinal survey batteries | Latent class / profile analysis (`stepmix`) | `survey_analytics` governs; select by BIC and entropy. |
| Irregular shapes, noise/outliers, unknown k | HDBSCAN (`hdbscan`) | Noise is a legitimate class, not a cluster to force; tune min_cluster_size. |
| Small n, want a hierarchy | Agglomerative (Ward) + dendrogram | Ward assumes Euclidean; read the dendrogram, do not cut at an arbitrary height. |
| High-dimensional feature space | Reduce first (PCA/MCA/FAMD), then cluster | UMAP/t-SNE are for visualization; validate any clustering done on an embedding — it distorts global distance. |

## Validation and stability contract
Every algorithm returns a partition even on uniform noise, so a solution is evidence only after it survives four checks. **Tendency:** confirm structure exists at all (a Hopkins statistic clearly off the ~0.5 random baseline toward the clustered pole — verify your implementation's direction, since the two conventions invert around 0.5 — or a non-uniform ordered dissimilarity image) before clustering. **Internal validity:** report silhouette, Davies-Bouldin, and Calinski-Harabasz — read them, do not blindly maximize one. **Stability:** bootstrap or subsample the data, re-cluster, and match clusters across resamples by Jaccard (the reference is R's `fpc::clusterboot`; in Python resample and match in the notebook). A cluster averaging below ~0.6 Jaccard is unstable; below ~0.5 it is indistinguishable from noise — drop or merge it. **Reproducibility:** define segments on one split, assign the holdout, and confirm the profiles hold. Reconcile the statistical count with the operational count: pick the smallest number of segments that is both stable and usable, and record why. Fix the seed for reproducibility, but never let one seed stand in for stability — report agreement across seeds.

```python
import numpy as np
from sklearn.utils import resample
from sklearn.metrics import silhouette_score

# `cluster(X)` is your chosen algorithm returning integer labels; keep it fixed across resamples.
labels = cluster(X)
valid = labels != -1                                     # HDBSCAN noise is coverage, not a cluster
valid_labels = np.unique(labels[valid])
noise_share = 1 - valid.mean()
print({"noise_share": noise_share})
if len(valid_labels) >= 2 and valid.sum() > len(valid_labels):
    print(silhouette_score(X[valid], labels[valid]))       # report; do not maximize blindly
else:
    print("silhouette undefined: fewer than two non-noise clusters")

jaccard = {c: [] for c in valid_labels}                   # bootstrap stability over non-noise clusters (ref: R fpc::clusterboot)
for _ in range(100):
    Xb, orig = resample(X, np.arange(len(X)))             # resample rows, keep original indices
    lb = cluster(Xb)
    for c in jaccard:                                     # match each base cluster to its most similar bootstrap cluster
        base = set(np.where(labels == c)[0]) & set(orig)
        jaccard[c].append(max((len(base & set(orig[lb == d])) / len(base | set(orig[lb == d]))
                               for d in np.unique(lb)), default=0.0))
# mean Jaccard per cluster: >~0.75 solid, 0.6–0.75 usable, <0.6 unstable, <0.5 noise — drop or merge.
```

## Actionability contract
A segmentation earns its keep only if the segments are **substantial** (large enough to operate on), **differentiable** (distinct on decision-relevant dimensions, not just on the clustering features), **accessible** (you can reach or act on them), and **actionable** (they imply *different* decisions). Enforce it: size every segment and refuse to ship one too small to operate; profile segments on **held-out descriptors not used to build them** — describing clusters by their own defining features is circular; name segments from evidence, not persona flavor text; and build a lightweight **typing/assignment model** (`predictive_modeling`) that classifies new units from routinely available fields, so the segmentation is deployable and monitorable rather than a one-off snapshot. Units migrate — schedule reassignment and re-validation, and treat segment drift as a monitored risk.

## Threats to validity (name and control each in the plan)
- **Clusters from noise** — every algorithm partitions even uniform data. Test tendency (Hopkins) and stability (bootstrap Jaccard) before believing segments.
- **Measurement-level mismatch** — k-means or PCA on one-hot categoricals or Likert items treats nominal/ordinal codes as interval and its centroids become meaningless. Use Gower/k-prototypes/FAMD, or latent-class methods via `survey_analytics`.
- **Scale dominance** — an unstandardized high-variance feature hijacks Euclidean distance. Standardize (robustly if skewed) before any distance-based method.
- **Curse of dimensionality** — distances concentrate in high dimensions and clusters blur. Select or reduce features first; validate, do not trust, clustering on embeddings.
- **Circular profiling** — characterizing segments by the very features that defined them. Profile on held-out variables and outcomes.
- **Outcome-vs-uplift confusion** — targeting by value or outcome level when the decision is about *responsiveness*; it wastes spend on sure-things and can backfire on sleeping-dogs. Use uplift / treatment-effect segmentation for intervention decisions.
- **Instability / seed dependence** — a solution that changes with seed or resample. Report multi-seed and bootstrap agreement; prefer a consensus solution.
- **Statistical-only k** — choosing the count by silhouette or BIC alone and shipping an inoperable number of segments. Reconcile with operational usability.
- **Segment drift** — a one-time segmentation that decays as units migrate. Ship a typing model and re-validate on a cadence.
- **Proxy discrimination** — segmenting on protected attributes or their proxies to drive pricing, credit, insurance, or targeting. Exclude protected attributes, audit proxies, and route regulated uses to the fairness/legal process.
- **Leakage in supervised/uplift segmentation** — `feature_engineering` owns fold-scoped construction; a value or uplift model that leaks the outcome mis-tiers everyone.

## Domain controls
Turn on a domain profile only when the user activates it; a profile is a technical control bundle, not proof of legal or regulatory compliance. When one is active: for **marketing / CRM**, keep value tiers, needs segments, and uplift targets distinct — they answer different questions — and exclude protected attributes and their proxies from targeting features; for **financial services**, treat any risk or value segmentation touching credit, pricing, or insurance as fair-lending/fair-pricing regulated — exclude protected classes and proxies, document the feature basis, and route to the documented human process, handling fraud clusters as anomaly detection with human review; for **healthcare / pharma**, preserve validated clinical definitions in patient phenotyping and HCP segmentation, route clinically consequential subgroups (e.g. a high-risk phenotype) to a qualified human, and check equity across protected groups; for **employee research**, suppress any segment, profile cell, or exported count with fewer than a default 5 members (raise the floor in the plan for smaller or more sensitive populations; never lower it) and apply complementary suppression so published segment totals cannot back-solve a suppressed small cell; for **public sector**, publish the method, the features, the stability evidence, and the assignment rule, and keep segments that allocate services transparent and contestable. Stop the sensitive output if a required control is unavailable.
