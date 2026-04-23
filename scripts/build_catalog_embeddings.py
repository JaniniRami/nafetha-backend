from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

# Ensure "app" imports work when running script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import PROFILE_MATCH_CACHE_PATH, PROFILE_MATCH_MODEL_NAME
from app.database import SessionLocal
from app.models import Community, CommunityEvent, ScrapedCompany, ScrapedJob, VolunteeringEvent
from app.profile_matching import (
    CatalogEmbeddingCache,
    DATASET_NAMES,
    EmbeddingDataset,
    encode_texts,
    normalize_embedding_text,
    save_catalog_embedding_cache,
)


def _clean_keywords_to_text(value: str | None) -> str:
    return normalize_embedding_text(value)


def _clean_description_to_text(value: str | None) -> str:
    return normalize_embedding_text(value)


def _join_keywords_and_description(keywords: str | None, description: str | None) -> str:
    keywords_clean = _clean_keywords_to_text(keywords)
    description_clean = _clean_description_to_text(description)
    if keywords_clean and description_clean:
        return f"{keywords_clean} {description_clean}"
    if keywords_clean:
        return keywords_clean
    if description_clean:
        return description_clean
    return ""


def _build_embeddings_dataset(rows: list[tuple[str, str]], model_name: str) -> EmbeddingDataset:
    ids: list[str] = []
    texts: list[str] = []
    for row_id, text_source in rows:
        cleaned = normalize_embedding_text(text_source)
        if not cleaned:
            continue
        ids.append(str(row_id))
        texts.append(cleaned)

    vectors = encode_texts(texts, model_name)
    return EmbeddingDataset(ids=ids, vectors=vectors)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build cached embeddings for catalog matching. "
            "Keyword sources: jobs.displayed_keywords, companies.displayed_keywords, "
            "communities.keywords, community_events.keywords, volunteering_events.keywords."
        )
    )
    parser.add_argument(
        "--output",
        default=PROFILE_MATCH_CACHE_PATH,
        help=f"Output .npz file path (default: {PROFILE_MATCH_CACHE_PATH})",
    )
    parser.add_argument(
        "--model",
        default=PROFILE_MATCH_MODEL_NAME,
        help=f"SentenceTransformers model name (default: {PROFILE_MATCH_MODEL_NAME})",
    )
    args = parser.parse_args()

    output_path = Path(args.output).expanduser().resolve()
    model_name = args.model.strip()

    db = SessionLocal()
    try:
        jobs_rows_raw = list(
            db.execute(
                select(
                    ScrapedJob.id,
                    ScrapedJob.displayed_keywords,
                    ScrapedJob.job_description,
                ).where(
                    (ScrapedJob.displayed_keywords.is_not(None) & (func.length(func.trim(ScrapedJob.displayed_keywords)) > 0))
                    | (ScrapedJob.job_description.is_not(None) & (func.length(func.trim(ScrapedJob.job_description)) > 0))
                )
            ).all()
        )
        companies_rows_raw = list(
            db.execute(
                select(
                    ScrapedCompany.id,
                    ScrapedCompany.displayed_keywords,
                    ScrapedCompany.about_us,
                ).where(
                    ScrapedCompany.blacklisted.is_(False),
                    (
                        (ScrapedCompany.displayed_keywords.is_not(None) & (func.length(func.trim(ScrapedCompany.displayed_keywords)) > 0))
                        | (ScrapedCompany.about_us.is_not(None) & (func.length(func.trim(ScrapedCompany.about_us)) > 0))
                    ),
                )
            ).all()
        )
        communities_rows = list(
            db.execute(
                select(Community.id, Community.keywords).where(
                    Community.keywords.is_not(None),
                    func.length(func.trim(Community.keywords)) > 0,
                )
            ).all()
        )
        community_events_rows = list(
            db.execute(
                select(CommunityEvent.id, CommunityEvent.keywords).where(
                    CommunityEvent.keywords.is_not(None),
                    func.length(func.trim(CommunityEvent.keywords)) > 0,
                )
            ).all()
        )
        volunteering_rows = list(
            db.execute(
                select(VolunteeringEvent.id, VolunteeringEvent.keywords).where(
                    VolunteeringEvent.keywords.is_not(None),
                    func.length(func.trim(VolunteeringEvent.keywords)) > 0,
                )
            ).all()
        )
    finally:
        db.close()

    jobs_rows: list[tuple[str, str]] = [
        (str(row_id), _join_keywords_and_description(raw_keywords, raw_description))
        for row_id, raw_keywords, raw_description in jobs_rows_raw
    ]
    companies_rows: list[tuple[str, str]] = [
        (str(row_id), _join_keywords_and_description(raw_keywords, raw_description))
        for row_id, raw_keywords, raw_description in companies_rows_raw
    ]
    communities_rows_clean: list[tuple[str, str]] = [
        (str(row_id), _clean_keywords_to_text(raw_keywords))
        for row_id, raw_keywords in communities_rows
    ]
    community_events_rows_clean: list[tuple[str, str]] = [
        (str(row_id), _clean_keywords_to_text(raw_keywords))
        for row_id, raw_keywords in community_events_rows
    ]
    volunteering_rows_clean: list[tuple[str, str]] = [
        (str(row_id), _clean_keywords_to_text(raw_keywords))
        for row_id, raw_keywords in volunteering_rows
    ]

    datasets = {
        "jobs": _build_embeddings_dataset(jobs_rows, model_name),
        "companies": _build_embeddings_dataset(companies_rows, model_name),
        "communities": _build_embeddings_dataset(communities_rows_clean, model_name),
        "community_events": _build_embeddings_dataset(community_events_rows_clean, model_name),
        "volunteering_events": _build_embeddings_dataset(volunteering_rows_clean, model_name),
    }

    embedding_dim = 0
    for dataset_name in DATASET_NAMES:
        vectors = datasets[dataset_name].vectors
        if vectors.size > 0:
            embedding_dim = int(vectors.shape[1])
            break

    cache = CatalogEmbeddingCache(
        model_name=model_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        embedding_dim=embedding_dim,
        datasets=datasets,
    )
    save_catalog_embedding_cache(cache, output_path)

    print(f"[profile-match] saved cache to: {output_path}", flush=True)
    print(f"[profile-match] model: {model_name}", flush=True)
    for dataset_name in DATASET_NAMES:
        print(
            f"[profile-match] {dataset_name}: {len(datasets[dataset_name].ids)} items",
            flush=True,
        )


if __name__ == "__main__":
    main()
