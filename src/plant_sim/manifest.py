"""Dataset manifest creation and verification helpers."""
import hashlib
import json
from pathlib import Path


def _artifact_entry(path: Path, root: Path) -> dict:
    return {
        "path": Path(__import__("os").path.relpath(path.resolve(), root.resolve())).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def refresh_manifest(output_dir: str | Path, extra_artifacts=(), preserve_declared=True, include_database=True) -> dict:
    """Refresh hashes for all important generated artifacts except the manifest itself."""
    root = Path(output_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    previous_artifacts=manifest.get("artifacts",{}) if preserve_declared else {}
    candidates = set(root.glob("*.csv")) | set(root.glob("*.json"))
    candidates.discard(manifest_path)
    if include_database:candidates.update(root.glob("*.sqlite"))
    candidates.update(Path(p) for p in extra_artifacts if Path(p).exists())
    artifacts = {}
    for relative,expected in previous_artifacts.items():
        previous_path=root/relative
        if not previous_path.is_file():
            artifacts[relative]=expected
        else:
            candidates.add(previous_path)
    for path in sorted(candidates, key=lambda p: str(p).casefold()):
        if path.is_file():
            entry = _artifact_entry(path, root)
            artifacts[entry["path"]] = entry
    manifest["artifacts"] = artifacts
    manifest["manifest_hash_note"] = "manifest.json is intentionally excluded because a file cannot contain its own stable SHA-256."
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(output_dir: str | Path) -> dict:
    root = Path(output_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {"valid": False, "errors": ["manifest.json is missing"], "verified_artifacts": 0}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    artifacts = manifest.get("artifacts", {})
    for relative, expected in artifacts.items():
        if expected.get("path",relative)!=relative:
            errors.append(f"declared path mismatch: {relative}")
        path = root / relative
        if not path.is_file():
            errors.append(f"missing artifact: {relative}")
            continue
        if path.stat().st_size != expected.get("size_bytes"):
            errors.append(f"size mismatch: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected.get("sha256"):
            errors.append(f"SHA-256 mismatch: {relative}")
    return {"valid": not errors, "errors": errors, "verified_artifacts": len(artifacts)}
