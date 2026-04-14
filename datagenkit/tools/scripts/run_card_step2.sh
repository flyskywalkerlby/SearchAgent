#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATAGENKIT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$DATAGENKIT_DIR"

python ./tools/merge_card_step2_inputs.py \
  --old-jsonl ../gt_optimization/gt/card_20251218_q2i_manucheck.jsonl \
  --new-jsonl ./outputs/gt_fix/card_image_multi_query_122b/card_gt_fix.jsonl \
  --root /srv/workspace/Kirin_AI_Workspace/AIC_I/g30064845/VLM/Chinese-CLIP/datasets/from_tuku_test_3k_together/card \
  --output-jsonl ./outputs/gt_fix/card_step2_candidates_merged.jsonl
