# Downloads the Kaikki Greek Wiktionary extracts. Run this in your terminal —
# the dumps are large and must NOT be pulled through an LLM session.
#
#   powershell pipelines/download_data.ps1
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

# ── Adding a new diachronic corpus AXIS (#40) ────────────────────────────────
# Each corpus stays on its OWN axis and is NEVER merged with another (cardinal
# rule). Leipzig (Wortschatz) ships several Greek corpora besides news — e.g.
# Wikipedia and web — at https://wortschatz.uni-leipzig.de/en/download/Greek.
# Download a few year-folders for ONE source (these are large — do NOT pull them
# through an LLM session), unpack them beside the existing ell_news_* folders in
# data/raw/, then run Layers B & C scoped to that source. --leipzig-source keeps
# the new corpus off the news axis; the axis label (e.g. 'wiki') is derived from it.
#
#   # e.g. ell_wikipedia_2016_1M, ell_wikipedia_2021_1M unpacked into data/raw/
#   # STOP the API first (it holds the SQLite WAL DB).
#   python pipelines/ingest/ingest_frequency_timeseries.py --leipzig-dir data/raw --leipzig-source wiki
#   python pipelines/ingest/ingest_diachronic.py        --leipzig-dir data/raw --leipzig-source wiki --pool-window 2
#   python pipelines/ingest/bootstrap_drift.py          --corpus wiki --k 12
#   # The new 'wiki' axis then appears automatically in the word page + Εξερεύνηση.
