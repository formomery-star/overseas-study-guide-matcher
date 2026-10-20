import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
files = [
    "database/v2/programs.json", "database/v2/evidence.json", "database/v2/taxonomy.json",
    "database/v2/jobs.json", "database/v2/direction_registry.json", "database/v2/contract.json",
    "database/universities.json", "database/evidence.json", "database/policy_sources.json",
    "database/recommendation_policy.json",
]
for p in sorted((root / "database/v2/subject_benchmarks").glob("*.json")):
    files.append(p.relative_to(root).as_posix())
hashes = {
    name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files
}
canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
print(json.dumps({"database_snapshot_sha256": hashes,
                   "snapshot_sha256": hashlib.sha256(canonical).hexdigest()}, ensure_ascii=False, indent=2))
