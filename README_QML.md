# QML dataset augmentation

This small tool augments the CICIoT-style CSVs in `dataset/` by adding features
that are useful when preparing data for Quantum Machine Learning (QML) models.

What it does:
- Adds per-row features: `coeff_var_Number`, `log_TotSize`, `flow_entropy`, `rate_normalized`, `pca_1`, `pca_2`.
- Fits global `StandardScaler` and `PCA` on a sampled subset (configurable) to avoid loading all CSVs.
- Writes augmented CSVs under `dataset_augmented/` preserving folder structure.

Quick start:

```powershell
# from repo root
python tools/augment_for_qml.py --dataset dataset --out dataset_augmented
```

Notes:
- The script assumes numeric column names like `Rate`, `Number`, `AVG`, `Std`, `Tot sum`, `Tot size` exist; adjust inside `tools/augment_for_qml.py` if your CSVs use different labels.
- The script does not change original files. It creates augmented copies.
- For very large repositories, consider running the script on a subset first to tune features.

Next steps:
- Add unit tests or small-run checks to validate types and ranges.
- Optionally add chunked/parallel processing for speed.
