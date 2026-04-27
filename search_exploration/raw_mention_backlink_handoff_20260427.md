# Raw Mention Backlink Image Search Handoff

Date: 2026-04-27

## Goal

Validate whether an Obsidian-style backlink route can add useful signal to image search.

This route should not be evaluated through Hindsight's original recall API first. The right first step is an offline, controlled experiment:

```text
caption JSON -> typed raw mentions -> mention/entity/relation indexes -> query-time linking -> image ranking
```

The core question is:

```text
Does raw mention backlink retrieval improve recall/ranking beyond BGE/BM25/CLIP, especially on vocabulary-gap and entity-composition queries?
```

## External Notes

I searched for related implementation patterns before fixing this plan.

### 1. Obsidian backlinks

Reference: https://help.obsidian.md/plugins/backlinks

Obsidian defines a backlink as an incoming link from one note to another. It also distinguishes:

- linked mentions: explicit internal links.
- unlinked mentions: text occurrences that match another note name.

Mapping to our image search:

```text
note              -> image
note name/concept -> raw mention phrase
backlink          -> mention -> images that contain it
unlinked mention  -> raw phrase occurrence from caption fields
```

Takeaway: the useful primitive is an inverse mention index, not a global ontology.

### 2. Inverted index / fielded search

Reference: https://lucene.apache.org/core/8_9_0/core/org/apache/lucene/index/package-summary.html

Lucene describes postings as a map from a term to the ordered list of documents containing that term. It also supports fields, so the same text in different fields can be treated differently.

Mapping to our image search:

```text
term/mention -> image postings
field/source -> 主旨 / 主体.动作 / 主体.上衣 / 整体环境.地点 / 剩余实体
```

Takeaway: keep source fields and mention types. Do not flatten everything into one BM25 string.

### 3. Property graph / GraphRAG

References:

- https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/
- https://neo4j.com/labs/genai-ecosystem/graphrag/

Both emphasize extracting entities/relationships, then combining graph retrieval with vector search. LlamaIndex also supports custom graph extractors and retrievers, including synonym and vector retrievers.

Mapping to our image search:

```text
custom extractor -> deterministic parser over our caption JSON
entity nodes     -> Human1 / Goods1 / Built1 local refs inside an image
relations        -> co_present / interacts_with / located_in / wears / holds
retrieval        -> exact/raw mention + mention embedding + entity-local composition
```

Takeaway: use a custom extractor based on our known JSON schema. Avoid asking an LLM to invent a full global concept graph.

### 4. Scene graph image retrieval

References:

- https://brown.stanford.edu/image-retrieval-using-scene-graphs/
- https://brown.columbia.edu/generating-semantically-precise-scene-graphs-from-textual-descriptions-for-improved-image-retrieval/

Scene graph image retrieval represents objects, attributes, and relationships, and uses these structures for complex queries such as a person holding something while wearing something.

Mapping to our image search:

```text
object/entity    -> Human1 / Goods1 / Built1
attributes       -> clothing, action, age, color, object category
relationships    -> subject-object interactions and co-presence
query structure  -> same-entity constraints, e.g. child + backpack + wearing/carrying
```

Takeaway: entity-local composition is the part most likely to differentiate this route from normal BM25.

## Current Caption Shape

From the existing handoff, one caption record looks like:

```json
{
  "raw_id": 0,
  "id": "00001",
  "image": "1_亲子_带小孩去海边沙滩旅行_Camera_xxx.jpg",
  "dataset_name": "life",
  "output": {
    "整体环境": {
      "事件类型": "亲子游玩",
      "时间": "白天",
      "地点": "海边",
      "天气": "晴天"
    },
    "主旨": "<Human1>蹲着玩耍的成年男子</Human1>与<Human2>蹲着玩耍的幼童</Human2>在沙滩上共同摆弄<Goods1>沙滩上的玩具组合</Goods1>，呈现温馨的亲子互动画面。",
    "主体": {
      "<Human1>": {"性别": "男", "年龄": "青年", "上衣": "白色短袖T恤", "动作": "蹲着", "相对位置": "右"},
      "<Human2>": {"性别": "男", "年龄": "儿童", "上衣": "白色蓝袖T恤", "动作": "蹲着", "相对位置": "左"},
      "<Goods1>": {"类别": "沙滩玩具", "外观特征": "黄色工程车,蓝色水桶,黄色铲子"}
    },
    "剩余实体": {"背景人群": "<Humans>"}
  }
}
```

The important property is that tags such as `<Human1>` connect the summary phrase in `主旨` to structured attributes in `主体`.

## Design Decision

Do not build a global standardized concept ontology.

Use typed raw mentions:

```text
raw phrase + source field + mention type + local entity ref
```

This avoids brittle normalization such as:

```text
父亲 == 成年男子 == 男性家长 == 爸爸
```

Instead, linking happens at query time through:

```text
query expansion + exact/substring match + mention embedding similarity + optional rerank
```

## Extraction Plan

For each image, produce one record with image-level mentions, entity-local mentions, and simple relations.

### Output Schema

```json
{
  "image_id": "life/xxx.jpg",
  "image": "xxx.jpg",
  "dataset": "life",
  "mentions": [
    {
      "text": "海边",
      "type": "location",
      "source": "整体环境.地点",
      "entity_ref": null,
      "weight": 1.0
    }
  ],
  "entities": [
    {
      "ref": "Human1",
      "entity_type": "person",
      "mentions": [
        {"text": "蹲着玩耍的成年男子", "type": "subject_phrase", "source": "主旨.tag_span", "weight": 1.0},
        {"text": "男", "type": "gender", "source": "主体.性别", "weight": 0.8},
        {"text": "青年", "type": "age", "source": "主体.年龄", "weight": 0.8},
        {"text": "白色短袖T恤", "type": "clothing", "source": "主体.上衣", "weight": 0.9},
        {"text": "蹲着", "type": "action", "source": "主体.动作", "weight": 0.9}
      ]
    }
  ],
  "relations": [
    {"head": "Human1", "rel": "co_present", "tail": "Human2", "source": "主旨", "weight": 0.5},
    {"head": "Human1", "rel": "interacts_with", "tail": "Goods1", "source": "主旨", "weight": 0.8}
  ]
}
```

### Field Rules

| Caption Field | Extraction | Notes |
|---|---|---|
| `主旨` tagged spans | complete span text, short noun/action phrase if easy | Highest value. Keeps entity-local meaning. |
| `主体` | every non-empty attribute value, split comma lists | Keep `entity_ref`; do not flatten only to image-level. |
| `整体环境` | event, time, location, weather | Useful for scene queries. |
| `剩余实体` | keys are mentions; values like `<Goods>` are not useful as text | Use keys, not generic tag values. |
| filename | optional weak signal only | Benchmark with and without it to avoid leakage. |

### Mention Types

Keep a small fixed set:

```text
subject_phrase
person_desc
object_phrase
gender
age
clothing
action
position
object_category
appearance
scene
event
location
time
weather
remaining_entity
filename_hint
```

Do not add a large ontology at this stage.

## Indexes

Build simple local JSON/Python indexes first.

```text
image_mentions.jsonl       # full extracted records
mention_to_images.json     # raw text -> image postings with source/type/entity_ref
entity_to_mentions.jsonl   # image + entity_ref -> local mention list
relation_edges.jsonl       # image-local entity relations
mention_embeddings.npy     # optional, for soft mention linking
```

The key inverse index is:

```json
{
  "沙滩玩具": [
    {"image_id": "life/xxx.jpg", "entity_ref": "Goods1", "type": "object_category", "source": "主体.类别", "weight": 1.0}
  ]
}
```

## Query Plan

At query time:

1. Keep the raw query.
2. Generate a small query expansion list.
3. Optionally parse coarse constraints such as person/object/action/scene.
4. Retrieve candidates from raw mention exact/substring hits.
5. Retrieve candidates from mention embedding similarity.
6. Add entity-local composition bonus when multiple constraints hit the same `entity_ref`.
7. Fuse with existing dense/visual routes only after backlink-only behavior is understood.

Example:

```text
query: 背着书包的孩子
expanded mentions: 背书包, 书包, 背包, 孩子, 儿童, 幼童, 小孩
entity-local bonus: same Human entity has child-like mention + backpack/clothing/object mention + carrying/wearing action
```

## Scoring

Start simple and interpretable.

### Backlink exact score

```text
score_exact(image) = sum(idf(mention) * field_weight * mention_weight)
```

### Soft mention score

```text
score_soft(image) = max/top-n similarity(query_or_expanded_mention, image_mentions)
```

### Entity-local composition bonus

```text
bonus_entity(image) = bonus if 2+ query constraints hit the same entity_ref
```

Examples:

```text
穿校服的男孩:
  same Human entity has boy-like mention + school-uniform-like clothing/action phrase

拿网球拍的女性:
  same Human entity has female-like mention + action/held-object mention related to tennis racket
```

### Final backlink score

```text
backlink_score = exact_score + soft_score + entity_local_bonus + relation_bonus
```

Normalize to 0-1 before fusion.

## Experiments

Keep the experiment list tight. Do not create many small branches of work.

### E0. Data and Extraction Validation

Purpose: make sure the parser is correct before running retrieval.

Run on the full caption JSON, then inspect a fixed sample of 50 images.

Checks:

- every image has `image_id` and `image`.
- tagged spans in `主旨` are captured.
- every `主体` key maps to an entity record.
- comma-separated attributes are split.
- no generic tag text such as `Human1` or `Goods1` is used as a searchable mention.
- no GT query/label is used in extraction.

Output:

```text
image_mentions.jsonl
extraction_stats.json
extraction_sample_50.md
```

### E1. Backlink Only Baseline

Purpose: determine whether raw mention backlinks have independent retrieval value.

Variants:

```text
E1a exact/substring mention index
E1b exact/substring + field weights
E1c exact/substring + entity-local composition bonus
```

Metrics:

```text
mAP
R@10
Recall@50
Recall@100
zero-hit query count
avg candidates per query
```

Output:

```text
backlink_only_eval.json
backlink_only_per_query.csv
```

### E2. Query-Time Expansion and Soft Linking

Purpose: test whether the route can solve vocabulary-gap queries without global concept standardization.

Variants:

```text
E2a raw query only
E2b rule/LLM query expansion + exact mention index
E2c query expansion + mention embedding search
E2d query expansion + mention embedding + entity-local composition
```

Important: expansion sees only the query and optional mention vocabulary. It must not see GT.

Output:

```text
backlink_expanded_eval.json
query_expansions.jsonl
```

### E3. Fusion With Existing Routes

Purpose: decide whether backlink is a candidate generator, a ranking signal, or not useful.

Compare:

```text
BGE(formatA)
BM25(formatA)
BGE + BM25
CLIP + BGE + BM25
CLIP + BGE + BM25 + backlink
```

If CLIP is not available locally, still run the text-side fusion first and leave CLIP fusion for the server.

Output:

```text
fusion_without_backlink_eval.json
fusion_with_backlink_eval.json
fusion_per_query_delta.csv
```

### E4. Error Analysis and Decision

Purpose: avoid shipping a route that only helps a few examples while hurting the overall ranking.

Analyze buckets:

```text
vocabulary_gap: 一家三口, 海边度假, 亲子互动
entity_composition: 穿校服的男孩, 背着书包的孩子, 拿网球拍的女性
object_scene: 沙滩玩具, 游乐园, 餐厅, 教室
fine_visual: 表情, 姿态, 小颜色差异
caption_missing: GT object exists visually but caption omitted it
```

Decision output:

```text
keep_as_recall_route
keep_as_fusion_signal
keep_only_query_expansion
skip
```

## Success Criteria

Backlink route is useful if at least one condition holds:

```text
Fusion mAP or R@10 improves by >= 1.0 absolute point without hurting major buckets.
Recall@100 improves by >= 3.0 absolute points, even if mAP does not improve.
Vocabulary-gap bucket has clear improvement and no severe precision collapse.
Entity-composition bucket improves compared with flat BM25.
```

Backlink route should be rejected or limited if:

```text
candidate count explodes with low precision.
soft mention matching duplicates BGE behavior with no incremental gain.
entity-local bonus creates many false positives.
overall fusion drops by > 0.5 point.
```

## Relation to Hindsight

Do not use Hindsight native recall API as the first benchmark for this route.

Recommended order:

```text
1. Offline extractor + index + evaluation.
2. If useful, map extracted mentions to Hindsight user-provided entities or metadata.
3. Use Hindsight only as a storage/service shell or hybrid retrieval reference, not as the source of truth for extraction quality.
```

Possible later Hindsight mapping:

```text
content       = formatA caption or compact mention text
metadata      = image_id, image_path, dataset
user_entities = raw mentions with type/source/entity_ref packed in metadata
chunks mode   = no LLM extraction, if we want deterministic entity data only
```

This avoids repeating the previous failure mode where Hindsight retained JSON caption text and the recall API could not perform full-gallery ranking.

## Implementation Notes

Start with deterministic parsing. Add LLM only at query expansion or rerank time.

Recommended first files if implemented later:

```text
search_experiments/backlink_line/extract_mentions.py
search_experiments/backlink_line/build_index.py
search_experiments/backlink_line/search_backlink.py
search_experiments/backlink_line/evaluate.py
search_experiments/backlink_line/README.md
```

Do not create a graph database dependency initially. Python dict / JSONL / numpy is enough for validation.

## Open Questions

- Which exact server caption JSON path should be the canonical source for this experiment?
- Should filename hints be disabled by default for fair benchmark reporting?
- Which embedding model should be used for mention-level soft linking: BGE text, same as caption BGE, or a smaller local model?
- Should query expansion be rule-based first, or use the available Qwen model directly?

## Bottom Line

This route should be tested as:

```text
typed raw mention backlinks + query-time expansion + entity-local composition
```

not as:

```text
global standardized concepts
Hindsight native recall
flat BM25 over JSON text
```
