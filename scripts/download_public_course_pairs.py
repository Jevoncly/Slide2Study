from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download licensed/public course-review pairs")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.root or Path(manifest["download_root"])
    records = []
    for source in manifest["sources"]:
        for pair in source.get("pairs", []):
            for role in ("courseware", "review"):
                for resource in pair.get(role, []):
                    target = root / source["source_id"] / pair["pair_id"] / role / resource["filename"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    request = urllib.request.Request(
                        resource["url"], headers={"User-Agent": "Slide2Study research dataset builder"}
                    )
                    with urllib.request.urlopen(request, timeout=60) as response:
                        payload = response.read()
                        content_type = response.headers.get_content_type()
                    if resource["filename"].endswith(".pdf") and not payload.startswith(b"%PDF"):
                        raise ValueError(f"Expected PDF content from {resource['url']}")
                    target.write_bytes(payload)
                    records.append(
                        {
                            "source_id": source["source_id"],
                            "pair_id": pair["pair_id"],
                            "topic": pair["topic"],
                            "role": role,
                            "path": str(target),
                            "url": resource["url"],
                            "content_type": content_type,
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "license": source["license"],
                            "redistribution": source["redistribution"],
                        }
                    )
    report = root / "download_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(records), "bytes": sum(r["bytes"] for r in records), "report": str(report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
