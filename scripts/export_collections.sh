#!/usr/bin/env bash
# Export every collection with mongoexport (one JSON file per collection) and zip them for submission.
set -euo pipefail

URI="${MONGO_URI:-mongodb://127.0.0.1:27017}"
DB="${MONGO_DB:-trailblazer}"
OUT="exports"

mkdir -p "$OUT"
for collection in trails users blacklist; do
  mongoexport --uri="$URI" --db="$DB" --collection="$collection" --jsonArray --pretty --out="$OUT/$collection.json"
done

rm -f trailblazer_collections.zip
(cd "$OUT" && zip -q ../trailblazer_collections.zip ./*.json)
echo "Created trailblazer_collections.zip"
