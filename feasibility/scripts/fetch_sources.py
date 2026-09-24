import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "pde-example.py": (
        "zwicker-group/py-pde",
        "09b7354c4732646db9de2b4f24c334d776fc45db",
        "examples/simple_pdes/simple.py",
    ),
    "pde-tests.py": (
        "zwicker-group/py-pde",
        "09b7354c4732646db9de2b4f24c334d776fc45db",
        "tests/pdes/test_diffusion_pdes.py",
    ),
    "pde-LICENSE": (
        "zwicker-group/py-pde",
        "09b7354c4732646db9de2b4f24c334d776fc45db",
        "LICENSE",
    ),
    "botorch-tutorial.ipynb": (
        "pytorch/botorch",
        "cd0249c60b2a81af0d91b5e7d462ef6f574fceec",
        "tutorials/multi_fidelity_bo/multi_fidelity_bo.ipynb",
    ),
    "botorch-LICENSE": (
        "pytorch/botorch",
        "cd0249c60b2a81af0d91b5e7d462ef6f574fceec",
        "LICENSE",
    ),
}


def main():
    receipts = []
    for filename, (repository, commit, relative_path) in SOURCES.items():
        url = f"https://raw.githubusercontent.com/{repository}/{commit}/{relative_path}"
        with urlopen(url, timeout=30) as response:
            payload = response.read()
        target = ROOT / "upstream" / filename
        target.write_bytes(payload)
        receipts.append({
            "file": str(target.relative_to(ROOT)),
            "url": url,
            "commit": commit,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        })
        (ROOT / "upstream" / "manifest.json").write_text(
            json.dumps(receipts, indent=2) + "\n"
        )
        print(f"FETCHED {filename}: {len(payload)} bytes", flush=True)


if __name__ == "__main__":
    main()
