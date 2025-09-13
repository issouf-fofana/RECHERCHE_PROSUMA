# apps/datasets/services.py
import csv
import io
import pandas as pd

def sniff_sep_and_encoding(fileobj, sample_size=4096):
    """
    Détecte séparateur et encodage à partir d'un file-like.
    Retourne (sep, encoding). Remet le curseur au début.
    """
    # lire un échantillon
    head = fileobj.read(sample_size)
    # bytes -> str
    if isinstance(head, bytes):
        try:
            text = head.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = head.decode("latin-1")
            encoding = "latin-1"
    else:
        text = head
        encoding = "utf-8"

    # détecter séparateur
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=[",", ";", "|", "\t"])
        sep = dialect.delimiter
    except Exception:
        sep = ","

    # reset curseur
    try:
        fileobj.seek(0)
    except Exception:
        pass

    return sep, encoding

def analyze_csv(django_file):
    """
    Lit un UploadedFile Django en le convertissant en flux texte
    (StringIO) pour pandas. Renvoie (df, header, rows, cols).
    """
    # détecter sep/encodage sur l'UploadedFile lui-même
    sep, enc = sniff_sep_and_encoding(django_file)

    # LIRE TOUT en mémoire puis convertir en texte (simple et sûr pour MVP)
    django_file.seek(0)
    data = django_file.read()        # bytes
    if isinstance(data, bytes):
        text = data.decode(enc, errors="replace")
    else:
        text = data                  # déjà str (rare)
    stream = io.StringIO(text)

    # lire avec pandas depuis un flux TEXTE
    df = pd.read_csv(stream, dtype=str, sep=sep, engine="python")

    header = list(df.columns)
    rows, cols = df.shape

    # remettre le curseur au début pour que Django puisse sauvegarder le fichier ensuite
    try:
        django_file.seek(0)
    except Exception:
        pass

    return df, header, rows, cols
