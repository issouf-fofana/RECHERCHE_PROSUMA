# apps/datasets/services.py
from __future__ import annotations

import os
from io import BytesIO
from typing import Tuple, List
import pandas as pd
import chardet
from django.core.files.storage import default_storage

_ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "cp1252", "latin1", "mac_roman"]

# -------------------------------------------------------------
# Détection séparateur / encodage
# -------------------------------------------------------------

def sniff_sep(bin_file_like) -> str:
    pos = bin_file_like.tell()
    raw = bin_file_like.read(64_000)
    bin_file_like.seek(pos)
    enc_guess = chardet.detect(raw or b"")["encoding"] or "utf-8"
    sample = (raw or b"").decode(enc_guess, errors="ignore")
    c_tab, c_sem, c_com = sample.count("\t"), sample.count(";"), sample.count(",")
    if c_tab > max(c_sem, c_com): 
        return "\t"
    return ";" if c_sem >= c_com else ","

def sniff_sep_and_encoding(bin_file_like) -> Tuple[str, str]:
    pos = bin_file_like.tell()
    raw = bin_file_like.read(64_000)
    bin_file_like.seek(pos)
    enc_guess = chardet.detect(raw or b"")["encoding"] or "utf-8"
    sample = (raw or b"").decode(enc_guess, errors="ignore")
    c_tab, c_sem, c_com = sample.count("\t"), sample.count(";"), sample.count(",")
    sep = "\t" if c_tab > max(c_sem, c_com) else (";" if c_sem >= c_com else ",")
    return sep, enc_guess

# -------------------------------------------------------------
# Lecture CSV/Excel robuste (support header param)
# -------------------------------------------------------------

def _read_csv_from_bytes(raw: bytes, *, sep: str | None = None, header: int | None = 0, nrows: int | None = None) -> pd.DataFrame:
    if sep is None:
        sep = sniff_sep(BytesIO(raw))
    last_err: Exception | None = None
    for enc in _ENCODING_CANDIDATES:
        try:
            return pd.read_csv(BytesIO(raw), dtype=str, sep=sep, encoding=enc, engine="python",
                               header=header, nrows=nrows)
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except Exception as e:
            # autre erreur (parser, etc.) -> on remonte
            raise e
    raise UnicodeDecodeError("encoding-detect", b"", 0, 1,
                             f"Echec décodage CSV (tests: {_ENCODING_CANDIDATES}). Dernière erreur: {last_err}")

def _read_excel_from_bytes(raw: bytes, *, header: int | None = 0, nrows: int | None = None) -> pd.DataFrame:
    return pd.read_excel(BytesIO(raw), dtype=str, sheet_name=0, header=header, nrows=nrows)

def read_any_dataframe_from_upload(file_obj, *, header: int | None = 0) -> pd.DataFrame:
    """
    Lecture d'un fichier uploadé (CSV/XLS/XLSX). `header` est 0-based (None => pas d'entêtes).
    """
    name = getattr(file_obj, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    raw = file_obj.read()  # la vue fera seek(0) ensuite

    if ext == ".csv":
        return _read_csv_from_bytes(raw, header=header)
    if ext in (".xlsx", ".xls"):
        return _read_excel_from_bytes(raw, header=header)
    if ext == ".pdf":
        raise ValueError("PDF non pris en charge (pas de tableau exploitable automatiquement).")
    raise ValueError(f"Extension non gérée: {ext}")

def analyze_file(file_obj) -> tuple[pd.DataFrame, List[str], int, int]:
    """
    Analyse par défaut avec `header=0`.
    """
    df = read_any_dataframe_from_upload(file_obj, header=0)
    df.columns = [str(c) for c in df.columns]
    header = list(df.columns)
    return df, header, int(len(df)), int(len(header))

# -------------------------------------------------------------
# Lecture depuis le storage (Dataset.file)
# -------------------------------------------------------------

def _open_raw_from_filefield(file_field) -> tuple[bytes, str]:
    storage = getattr(file_field, "storage", default_storage)
    name = getattr(file_field, "name", None)
    if not name or not storage.exists(name):
        return b"", ""
    with storage.open(name, "rb") as fh:
        raw = fh.read()
    return raw, name

def read_dataset_dataframe(obj_with_file, *, header_row: int | None = 0) -> tuple[pd.DataFrame | None, str | None]:
    """
    Ouvre un FileField (p.ex. Dataset.file) et lit CSV/XLS/XLSX.
    Retourne (df, None) ou (None, 'missing').
    """
    file_field = getattr(obj_with_file, "file", obj_with_file)
    raw, name = _open_raw_from_filefield(file_field)
    if not name:
        return None, "missing"

    ext = os.path.splitext(name)[1].lower()
    if ext == ".csv":
        df = _read_csv_from_bytes(raw, header=header_row)
    elif ext in (".xlsx", ".xls"):
        df = _read_excel_from_bytes(raw, header=header_row)
    else:
        raise ValueError(f"Extension non prise en charge pour la comparaison: {ext}")

    df.columns = [str(c) for c in df.columns]
    return df, None

def peek_rows_for_header(obj_with_file, *, max_rows: int = 10) -> list[list[str]]:
    """
    Retourne les `max_rows` premières lignes sans entêtes (pour choisir la ligne d'entêtes).
    """
    file_field = getattr(obj_with_file, "file", obj_with_file)
    raw, name = _open_raw_from_filefield(file_field)
    if not name:
        return []

    ext = os.path.splitext(name)[1].lower()
    if ext == ".csv":
        df = _read_csv_from_bytes(raw, header=None, nrows=max_rows)
    elif ext in (".xlsx", ".xls"):
        df = _read_excel_from_bytes(raw, header=None, nrows=max_rows)
    else:
        return []

    # Convertit en liste de listes (str)
    rows: list[list[str]] = []
    for _, row in df.iterrows():
        rows.append([("" if pd.isna(v) else str(v)) for v in row.tolist()])
    return rows

# -------------------------------------------------------------
# Heuristique magasin (à adapter)
# -------------------------------------------------------------

def infer_store_from_filename(filename: str) -> tuple[str | None, str | None]:
    base = os.path.basename(filename or "")
    code, name = None, None
    try:
        if "xsupplierorder" in base:
            code = base.split("xsupplierorder", 1)[0].strip().strip("_-")
            code = "".join(ch for ch in code if ch.isdigit())
    except Exception:
        pass
    return code or None, name or None
