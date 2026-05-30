# Downloads the Kaikki Greek Wiktionary extracts. Run this in your terminal —
# the dumps are large and must NOT be pulled through an LLM session.
#
#   pwsh pipelines/download_data.ps1
#
# Verify the current URLs at https://kaikki.org/ before running (Kaikki paths
# change with each dump). Below are the canonical extract locations.

$ErrorActionPreference = "Stop"
$raw = "data/raw"
New-Item -ItemType Directory -Force -Path $raw | Out-Null

# Greek-edition Wiktionary (el): native Greek definitions.
$elUrl = "https://kaikki.org/dictionary/downloads/el/el-extract.jsonl.gz"
# English-edition Wiktionary, Greek entries only: often richer inflection tables.
$enUrl = "https://kaikki.org/dictionary/Greek/kaikki.org-dictionary-Greek.jsonl"

Write-Host "Downloading el extract..."
Invoke-WebRequest -Uri $elUrl -OutFile "$raw/el-extract.jsonl.gz"
Write-Host "Decompressing el extract..."
$in  = [System.IO.File]::OpenRead("$raw/el-extract.jsonl.gz")
$out = [System.IO.File]::Create("$raw/el-extract.jsonl")
$gz  = New-Object System.IO.Compression.GzipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
$gz.CopyTo($out); $gz.Dispose(); $out.Dispose(); $in.Dispose()

Write-Host "Downloading en (Greek-entries) extract..."
Invoke-WebRequest -Uri $enUrl -OutFile "$raw/en-extract.jsonl"

Write-Host "Done. Files in $raw/. Next:"
Write-Host "  python pipelines/ingest/ingest_kaikki.py --input data/raw/el-extract.jsonl --source el-wiktionary --limit 5000"
Write-Host "  python pipelines/ingest/ingest_kaikki.py --input data/raw/en-extract.jsonl --source en-wiktionary --limit 5000"
Write-Host "  python pipelines/ingest/build_search_index.py"
