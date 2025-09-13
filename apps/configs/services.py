def validate_columns(selected, headers):
    missing = [c for c in selected if c not in headers]
    if missing:
        raise ValueError(f"Colonnes invalides: {missing}")
