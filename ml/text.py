import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from ml.data import load

TYPICALITY_FILE = "lot_typicality.npz"
STEM_LENGTH = 6
WORD_RE = re.compile(r"[а-яёa-z]{3,}")

DOCS_SQL = "SELECT lot_id, coalesce(subject, '') AS text FROM announcements"


def stems(text: str) -> list[str]:
    return [word[:STEM_LENGTH] for word in WORD_RE.findall(text.lower())]


def lot_typicality(lots: pd.DataFrame, refresh: bool = False) -> pd.Series:
    docs = load("subjects_docs", DOCS_SQL, refresh)
    docs = docs.merge(lots[["lot_id", "okpd_group"]], on="lot_id")
    vectorizer = TfidfVectorizer(analyzer=stems, min_df=5, max_features=50000, sublinear_tf=True)
    matrix = normalize(vectorizer.fit_transform(docs["text"]))

    codes, groups = pd.factorize(docs["okpd_group"])
    membership = sparse.csr_matrix((np.ones(len(codes)), (codes, np.arange(len(codes)))), shape=(len(groups), len(codes)))
    centroids = normalize(membership @ matrix)
    similarity = np.zeros(len(codes), dtype=np.float32)
    for group in range(len(groups)):
        rows = np.flatnonzero(codes == group)
        similarity[rows] = (matrix[rows] @ centroids[group].T).toarray().ravel()
    return pd.Series(similarity, index=docs["lot_id"].to_numpy(), name="typicality")


def save_typicality(typicality: pd.Series, model_dir: Path) -> None:
    ordered = typicality.sort_index()
    np.savez_compressed(
        model_dir / TYPICALITY_FILE,
        lot_ids=ordered.index.to_numpy(dtype=np.int64),
        values=ordered.to_numpy(dtype=np.float32),
    )
