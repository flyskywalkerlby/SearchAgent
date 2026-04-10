#!/bin/zsh
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <test_imgs_images.jsonl>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATAGENKIT_DIR="$REPO_DIR/datagenkit"
TEMPLATE_CONFIG="$DATAGENKIT_DIR/configs/gt_fix/test_imgs_image_multi_query_122b.yaml"

IMAGE_JSONL="$1"
TMP_CONFIG="$(mktemp /tmp/test_imgs_gt_fix_config.XXXXXX.yaml)"
trap 'rm -f "$TMP_CONFIG"' EXIT

sed "s|/path/to/test_imgs_images.jsonl|$IMAGE_JSONL|g" "$TEMPLATE_CONFIG" > "$TMP_CONFIG"

cd "$DATAGENKIT_DIR"
python main.py --config "$TMP_CONFIG"
