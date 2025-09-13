import pandas as pd

def compute_diff(df1, df2, cfg):
    # Colonnes à conserver
    df1 = df1[cfg.columns_web1].copy()
    df2 = df2[cfg.columns_desktop].copy()

    # Listes de clés (compat old: str -> list)
    k1 = cfg.join_key_web1 if isinstance(cfg.join_key_web1, list) else [cfg.join_key_web1]
    k2 = cfg.join_key_desktop if isinstance(cfg.join_key_desktop, list) else [cfg.join_key_desktop]

    # Jointure composite (respecte l’ordre des clés)
    merged = pd.merge(
        df1, df2,
        left_on=k1, right_on=k2,
        how=cfg.join_type or "outer",
        suffixes=("_web1", "_desktop"),
        indicator=True
    )

    # Écarts d’existence
    mask_side = merged["_merge"] != "both"

    # Écarts de valeurs sur colonnes communes (hors clés)
    commons = (set(cfg.columns_web1) - set(k1)) & (set(cfg.columns_desktop) - set(k2))
    mask_values = False
    for c in commons:
        c1, c2 = f"{c}_web1", f"{c}_desktop"
        if c1 in merged.columns and c2 in merged.columns:
            m = (merged[c1] != merged[c2])
            mask_values = m if isinstance(mask_values, bool) else (mask_values | m)

    diff = merged[mask_side | (False if isinstance(mask_values, bool) else mask_values)].copy()

    # Sécuriser types
    if "_merge" in diff.columns:
        diff["_merge"] = diff["_merge"].astype(str)

    return diff
