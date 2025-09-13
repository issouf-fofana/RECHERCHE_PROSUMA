# apps/comparisons/exporters.py
import re
import pandas as pd

# Caractères interdits par Excel / XML
_ILLEGAL_XLSX_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')

def _sanitize_excel_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):  # NaN
        return ""
    s = str(v)
    return _ILLEGAL_XLSX_RE.sub("", s)

def _sanitize_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    safe = df.copy()

    # Colonnes -> string nettoyée
    safe.columns = [_sanitize_excel_text(c) for c in safe.columns]

    # Cellules objet/texte -> string nettoyée
    for col in safe.columns:
        if safe.dtypes[col] == "object" or str(safe.dtypes[col]).startswith(("string", "unicode")):
            safe[col] = safe[col].map(_sanitize_excel_text)

    return safe

def to_csv(df: pd.DataFrame, path):
    df.to_csv(path, index=False)

def to_xlsx(df: pd.DataFrame, path, sheet_name: str = "Diff"):
    safe = _sanitize_df_for_excel(df)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        safe.to_excel(writer, index=False, sheet_name=sheet_name)
