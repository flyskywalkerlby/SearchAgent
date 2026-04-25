# Hindsight Image Search Experiment Plan

Date: 2026-04-25

Goal: determine the right role for Hindsight in image search with existing image captions, without repeating experiments that have already been run unless the previous setup was likely the wrong variant.

## Context

Current input is scattered images with captions. Images do not currently have reliable time, location, or event metadata beyond what may appear in the caption itself.

Hindsight stores and searches `memory_units`, not images directly. For image search, the intended mapping is:

- image = document
- `image_id` or `image_path` = `document_id`
- caption text = `content`
- path, dataset, filename, caption source = `metadata`
- dataset/source filters = `tags`
- final output = aggregate fact-level results back to image-level ranking by `document_id`

## What Was Already Tried

From `搜索探索_v2_20260425_1630.md`:

- Hindsight `recall API` + structured JSON caption + jieba BM25 + BGE.
- DB direct search + BGE(JSON) + jieba BM25 + RRF.
- BGE(JSON) single route.
- jieba BM25 single route.
- BGE(JSON) + BM25 RRF.
- BM25 vocabulary-gap diagnosis.
- BGE(JSON) vs BGE(format-A plain text) comparison.
- Conclusion that raw Hindsight `recall API` is not a good full-gallery image ranking interface.

These should not be repeated in the same form.

## Experiment Table

| ID | Experiment | Prior Status | Run? | Purpose | Difference From Prior Work |
|---|---|---:|---:|---|---|
| E0 | Standardize input data | Not done | Yes | Make captions, image paths, GT, and dataset names comparable and reproducible | Previous experiments used scattered paths/formats |
| E1 | Hindsight recall + JSON caption | Done | No | Original recall API baseline | Already showed very low mAP |
| E2 | DB direct + JSON BGE + jieba BM25 | Done | No | Original DB-direct baseline | Already showed mAP around 60 |
| E3 | Hindsight recall + format-A caption + chunks | Not done | Yes | Test whether better caption text plus no LLM extraction improves recall API | Previous run used JSON + verbatim |
| E4 | DB direct + format-A BGE | Partially done outside Hindsight DB | Yes | Verify Hindsight DB embedding ranking can reproduce v1 BGE(format-A) | Previous format-A score came from v1 pipeline |
| E5 | DB direct + format-A BGE + jieba BM25 | Not fully done | Yes | Test whether BM25 still helps when caption text is correct | Previous BM25 used JSON text |
| E6 | Query expansion + BM25 | Diagnosed only | Yes | Address vocabulary gap such as "一家三口" vs "父亲 母亲 宝宝 亲子" | Previous work diagnosed the issue but did not evaluate expansion |
| E7 | Query expansion + BGE + BM25 RRF | Not done | Yes | Check whether expanded sparse query improves hybrid search | New variable |
| E8 | Image-level aggregation adapter | Not done | Yes | Convert fact-level recall into image-level ranking | Previous work mostly ranked fact/result rows directly |
| E9 | Hindsight graph/entity links | Not sufficiently isolated | Optional | Test whether explicit entities make graph expansion useful | Previous conclusion may be premature because entities were not designed for image captions |
| E10 | Multi-facet caption ingestion | Not done | Optional later | Test summary/subject/scene/object units and aggregation | Caption is short now, so one-caption-per-image is first priority |
| E11 | CLIP + Hindsight text hybrid | Similar v1 work exists | Yes | Check whether Hindsight text score can become one route in the strongest v1 fusion | Previous CLIP+BGE used v1 text scores, not Hindsight text output |
| E12 | LLM rerank on Hindsight candidates | Similar v1 work exists | Optional | Check whether Hindsight candidate sets are good for LLM reranking | Previous LLM rerank used v1 candidates |
| E13 | Full pipeline benchmark | Not done | Yes | Freeze reproducible benchmark and final conclusion | Summarizes all useful routes |

## Recommended Execution Order

| Phase | Experiments | Goal |
|---|---|---|
| P0 | E0 | Standardize all inputs before running more numbers |
| P1 | E3, E4 | Re-test Hindsight with the right caption format |
| P2 | E5, E6, E7 | Evaluate BM25 and query expansion value |
| P3 | E8 | Fix the mismatch between fact-level Hindsight output and image-level search |
| P4 | E11 | Fuse Hindsight text signals with CLIP |
| P5 | E9, E10, E12 | Run only if earlier phases show useful signal |
| P6 | E13 | Write final benchmark and recommendation |

## Standard Data Format

`captions_standard.jsonl`

```json
{
  "image_id": "life/xxx.jpg",
  "image": "xxx.jpg",
  "root": "/srv/.../test_imgs_rename",
  "image_path": "/srv/.../test_imgs_rename/xxx.jpg",
  "dataset": "life",
  "caption_format_a": "自然语言/格式A纯文本 caption",
  "caption_json": {},
  "keywords": []
}
```

`gt_standard.jsonl`

```json
{
  "query": "一家三口",
  "images": ["xxx.jpg", "yyy.jpg"]
}
```

Validation:

- `image_id` is unique.
- Every GT image can map to one `image_id`.
- `caption_format_a` is non-empty.
- `image_path` can be reconstructed from `root + image`.

## Hindsight Ingestion Baseline

Start with one caption per image. Do not split into facets until E10.

Environment:

```bash
export HINDSIGHT_API_RETAIN_EXTRACTION_MODE=chunks
export HINDSIGHT_API_RETAIN_EXTRACT_CAUSAL_LINKS=false
export HINDSIGHT_API_RERANKER_PROVIDER=rrf
export HINDSIGHT_API_ENABLE_OBSERVATIONS=false
```

Retain item:

```python
{
    "content": caption_format_a,
    "document_id": image_id,
    "event_date": None,
    "metadata": {
        "image_id": image_id,
        "image": image,
        "root": root,
        "image_path": image_path,
        "dataset": dataset,
        "caption_source": "format_a"
    },
    "tags": [f"dataset:{dataset}"]
}
```

Expected checks after ingestion:

- number of documents equals number of images.
- number of memory units is approximately number of images.
- every memory unit has a `document_id`.
- every result can be mapped back to `metadata.image_path`.

## Experiment Details

### E3: Recall API + Format-A + Chunks

Purpose: verify whether the poor Run1 result was caused by the API shape itself, or by JSON caption + verbatim ingestion.

Run with:

- `caption_format_a`
- `retain_extraction_mode=chunks`
- one image = one document = one memory unit
- large enough `max_tokens` for recall
- tags filter for dataset

Success/failure interpretation:

- If still very low, raw `recall_async` should not be used as the final image search API.
- If much better, keep it as a candidate route but still compare against DB-direct full ranking.

### E4: DB Direct + Format-A BGE

Purpose: verify that Hindsight DB stores the same embedding signal as the v1 BGE(format-A) route.

If result does not match v1 BGE roughly:

- check same BGE model.
- check same input text.
- check same normalization.
- check image id alignment.

### E5: DB Direct + Format-A BGE + Jieba BM25

Purpose: evaluate BM25 contribution when the indexed text is the correct caption text, not JSON.

Compare:

- BGE(format-A) only.
- jieba BM25(format-A) only.
- BGE(format-A) + jieba BM25 RRF.

### E6: Query Expansion + BM25

Purpose: solve sparse retrieval vocabulary gap.

Expansion tiers:

- rule dictionary.
- LLM rewrite.
- query to sparse keywords only.

Examples:

```text
一家三口 -> 父亲 母亲 孩子 宝宝 亲子 家庭 三口之家
海边度假 -> 海边 沙滩 海水 旅行 游玩 度假
```

### E7: Query Expansion + Hybrid

Compare:

- BGE original query + BM25 original query.
- BGE original query + BM25 expanded query.
- BGE expanded query + BM25 expanded query.
- BGE original query + BGE expanded query + BM25 expanded query.

Do not assume expanded query helps dense retrieval; evaluate it separately.

### E8: Image-Level Aggregation Adapter

Purpose: Hindsight returns facts, but the product needs images.

Aggregation strategies:

- max fact score per image.
- top-n fact score sum per image.
- weighted score by facet if E10 is enabled later.
- BM25 bonus or dense score bonus.

Output schema:

```json
{
  "query": "一家三口",
  "results": [
    {
      "image_id": "life/xxx.jpg",
      "image_path": "/srv/.../xxx.jpg",
      "score": 0.91,
      "rank": 1,
      "matched_units": [
        {
          "text": "caption text",
          "source": "semantic",
          "score": 0.87
        }
      ]
    }
  ]
}
```

### E9: Entity Links

Optional. Run only after E3-E8.

Use explicit entities from caption, for example:

```json
[
  {"text": "亲子", "type": "relationship"},
  {"text": "幼童", "type": "person"},
  {"text": "沙滩", "type": "scene"}
]
```

Goal: check whether graph expansion adds meaningful recall beyond dense/BM25.

### E10: Multi-Facet Captions

Optional. Run only if one-caption-per-image has a ceiling.

Candidate facets:

- summary
- subject
- action
- scene
- object
- keywords

Each facet should keep `metadata.image_id`, and final ranking must aggregate to image level.

### E11: CLIP + Hindsight Text Hybrid

Purpose: test whether Hindsight text score can be one route in the strongest v1 fusion.

Compare:

- CLIP only.
- CLIP + v1 BGE.
- CLIP + Hindsight BGE.
- CLIP + Hindsight BGE + expanded BM25.

### E12: LLM Rerank on Hindsight Candidates

Optional. Only useful if Hindsight candidate quality is acceptable.

Compare:

- v1 candidates + LLM rerank.
- Hindsight candidates + LLM rerank.
- fused candidates + LLM rerank.

## Must-Do / Optional / Skip

Must-do:

```text
E0, E3, E4, E5, E6, E7, E8, E11, E13
```

Optional:

```text
E9, E10, E12
```

Skip exact repeats:

```text
E1, E2
```

## First Batch To Run

Run these first:

1. E0: standardize input.
2. E3: recall + format-A + chunks.
3. E4: DB direct + format-A BGE.
4. E5: DB direct + format-A BGE + jieba BM25.
5. E6: query expansion + BM25.

After these five, decide whether Hindsight should stay as:

- a main text retrieval service,
- a BM25/metadata auxiliary signal,
- or only an experiment reference.
