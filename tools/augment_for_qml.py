"""
augment_for_qml.py

Scan dataset CSVs, compute additional features useful for Quantum ML models,
and write augmented CSVs under dataset_augmented/. The script fits global
scalers/PCA on a sampled subset to avoid loading all files into memory.

New features added (per-flow / per-row):
 - coeff_var_Number: coefficient of variation = Std / AVG (robustness to scale)
 - log_TotSize: log1p(Tot size) to reduce skew
 - rate_normalized: Rate normalized by fitted StandardScaler
 - flow_entropy: approximate entropy across protocol one-hot columns (HTTP..LLC)
 - pca_1..pca_2: first 2 PCA components fitted on selected numeric features

Usage: run from repo root: python tools/augment_for_qml.py --dataset dataset --out dataset_augmented
"""

from pathlib import Path
import argparse
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA


PROTO_COLS = [
    "HTTP","HTTPS","DNS","Telnet","SMTP","SSH","IRC",
    "TCP","UDP","DHCP","ARP","ICMP","IGMP","IPv","LLC"
]


def list_csvs(root: Path):
    return list(root.rglob('*.csv'))


def sample_numeric_rows(paths, n_per_file=200):
    cols_keep = None
    samples = []
    for p in paths:
        try:
            df = pd.read_csv(p, nrows=n_per_file)
        except Exception:
            continue
        if cols_keep is None:
            cols_keep = df.columns.tolist()
        samples.append(df)
    if not samples:
        return pd.DataFrame()
    return pd.concat(samples, ignore_index=True)


def compute_flow_entropy(df):
    # treat PROTO_COLS as nominal probabilities (they appear like 0/1 or fractions)
    present = [c for c in PROTO_COLS if c in df.columns]
    if not present:
        return np.zeros(len(df))
    probs = df[present].values.astype(float)
    # normalize per-row
    row_sums = probs.sum(axis=1, keepdims=True)
    # avoid divide by zero
    row_sums[row_sums == 0] = 1.0
    pnorm = probs / row_sums
    # entropy
    with np.errstate(divide='ignore', invalid='ignore'):
        ent = -np.nansum(np.where(pnorm>0, pnorm * np.log2(pnorm), 0.0), axis=1)
    return ent


def angle_encoding(x, max_val=None):
    # Map a positive numeric value to an angle in [0, pi] then encode as sin, cos
    x = np.array(x, dtype=float)
    # sanitize values
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    if max_val is None:
        max_val = np.nanmax(x) if x.size else 1.0
    # avoid zero or negative max
    max_val = float(max_val) if (max_val is not None and np.isfinite(max_val) and max_val > 0) else 1.0
    theta = np.pi * (x / max_val)
    return np.sin(theta), np.cos(theta)


def augment_file(p: Path, out_root: Path, scaler: StandardScaler, pca: PCA, dataset_root: Path, split_ratio=0.8):
    try:
        df = pd.read_csv(p)
    except Exception:
        return
    # basic new features
    df['coeff_var_Number'] = np.where(df['AVG'] != 0, df['Std'] / (df['AVG'] + 1e-9), 0.0)
    if 'Tot size' in df.columns:
        df['log_TotSize'] = np.log1p(df['Tot size'])
    else:
        df['log_TotSize'] = 0.0

    # flow entropy
    df['flow_entropy'] = compute_flow_entropy(df)

    # numeric features for scaling / PCA
    numeric_candidates = [c for c in ['Rate','Number','AVG','Std','Tot sum','Tot size'] if c in df.columns]
    X = df[numeric_candidates].fillna(0.0).astype(float).values
    # sanitize values: replace inf/nan and clip to reasonable range
    X = np.nan_to_num(X, nan=0.0, posinf=np.finfo(np.float64).max/1e6, neginf=-np.finfo(np.float64).max/1e6)
    # clip extreme outliers to avoid numerical issues
    clip_val = 1e12
    X = np.clip(X, -clip_val, clip_val)
    if scaler is not None and hasattr(scaler, 'transform'):
        rate_norm = scaler.transform(X)[:, 0] if X.shape[1] >= 1 else np.zeros(len(df))
    else:
        rate_norm = df['Rate'].astype(float).values if 'Rate' in df.columns else np.zeros(len(df))
    df['rate_normalized'] = rate_norm

    # PCA components
    if pca is not None and X.shape[1] >= pca.n_components_:
        comps = pca.transform(X)
        for i in range(min(2, comps.shape[1])):
            df[f'pca_{i+1}'] = comps[:, i]
    else:
        df['pca_1'] = 0.0
        df['pca_2'] = 0.0

    # angle encodings for Rate and log_TotSize
    max_rate = df['Rate'].max() if 'Rate' in df.columns else 1.0
    s_r, c_r = angle_encoding(df['Rate'].fillna(0.0).astype(float).values, max_val=max_rate)
    df['rate_sin'] = s_r
    df['rate_cos'] = c_r
    max_ts = df['log_TotSize'].max() if 'log_TotSize' in df.columns else 1.0
    s_t, c_t = angle_encoding(df['log_TotSize'].fillna(0.0).astype(float).values, max_val=max_ts)
    df['logTot_sin'] = s_t
    df['logTot_cos'] = c_t

    # write to output preserving folder; compute relative path robustly
    try:
        rel = p.resolve().relative_to(dataset_root.resolve())
    except Exception:
        # fallback to using name only
        rel = Path(p.name)
    outp = out_root / rel
    outp.parent.mkdir(parents=True, exist_ok=True)
    try:
        n = len(df)
        if n > 10:
            cut = int(split_ratio * n)
            df.iloc[:cut].to_csv(outp, index=False)
            df.iloc[cut:].to_csv(outp.with_name(outp.stem + '_test.csv'), index=False)
        else:
            df.to_csv(outp, index=False)
    except Exception:
        df.to_csv(outp, index=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=str, default='dataset')
    parser.add_argument('--out', type=str, default='dataset_augmented')
    parser.add_argument('--sample-per-file', type=int, default=200)
    parser.add_argument('--limit-files', type=int, default=0, help='limit to first N files for testing')
    parser.add_argument('--train-split', type=float, default=0.8, help='train split ratio per file')
    args = parser.parse_args()

    root = Path(args.dataset)
    out_root = Path(args.out)
    paths = list_csvs(root)
    if args.limit_files and args.limit_files > 0:
        paths = paths[:args.limit_files]
    print(f'Found {len(paths)} CSV files')

    # sample to fit scaler/PCA
    sampled = sample_numeric_rows(paths, n_per_file=args.sample_per_file)
    numeric_candidates = [c for c in ['Rate','Number','AVG','Std','Tot sum','Tot size'] if c in sampled.columns]
    if not numeric_candidates:
        print('No numeric candidate columns found for scaler/PCA; writing files with basic features only')
        scaler = None
        pca = None
    else:
        Xs = sampled[numeric_candidates].fillna(0.0).astype(float).values
        scaler = StandardScaler().fit(Xs)
        # fit PCA to 2 components or less
        n_comp = min(2, Xs.shape[1])
        pca = PCA(n_components=n_comp).fit(scaler.transform(Xs))

    # augment each file
    for p in paths:
        augment_file(p, out_root, scaler, pca, dataset_root=root, split_ratio=args.train_split)

    print('Augmentation complete. Augmented files saved under', out_root)
