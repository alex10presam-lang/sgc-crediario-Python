"""Create a source-only distribution, with an explicit allowlist and no Git history."""

import hashlib
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("sgc", "tests", "docs", "tools", ".github")
FILES = (
    "README.md",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    ".gitignore",
    ".streamlit/config.toml",
    "dashboard.py",
    "run.py",
)
FORBIDDEN = {".db", ".sqlite", ".sqlite3", ".enc", ".pem", ".key", ".pyc", ".pyd", ".exe"}


def export():
    paths = {ROOT / name for name in FILES}
    for folder in FOLDERS:
        paths.update(path for path in (ROOT / folder).rglob("*") if path.is_file())
    valid = []
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if "__pycache__" in relative.parts or ".pytest_cache" in relative.parts:
            continue
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError("Arquivo obrigatório ausente ou fora do projeto: " + str(relative))
        if path.suffix.lower() in FORBIDDEN or path.name in {
            "secrets.toml",
            ".env",
            "service_account.json",
        }:
            raise RuntimeError("Arquivo de uso não permitido: " + str(relative))
        if path.suffix.lower() in {".py", ".md", ".txt", ".toml", ".yml", ".json"}:
            content = path.read_text(encoding="utf-8")
            if re.search(r"-----BEGIN [A-Z ]*PRIVATE" + r" KEY-----", content):
                raise RuntimeError("Chave privada detectada em " + str(relative))
            if re.search(r"gh[pousr]_[a-zA-Z0-9]{30,}|github_pat_[a-zA-Z0-9_]{40,}", content):
                raise RuntimeError("Token detectado em " + str(relative))
        valid.append((path, relative))
    output = ROOT / "data" / "exports" / "sgc-portfolio.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path, relative in valid:
            archive.write(path, Path("sgc-portfolio") / relative)
    return output, hashlib.sha256(output.read_bytes()).hexdigest(), len(valid)


if __name__ == "__main__":
    path, digest, count = export()
    print(f"Pacote criado: {path}\nArquivos: {count}\nSHA-256: {digest}")
