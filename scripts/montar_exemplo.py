"""Copia o deck NEXUS-GO para o plugin como o projeto de exemplo (etapa 5, docs/plano-etapas-2-4-5.md).

Uso: python scripts/montar_exemplo.py <pasta do kit>
Lê o kit e não muda nada nele. Escreve plugin/plugins/deck-studio/templates/exemplo-nexus-go/, um retrato do kit no
dia: o conteúdo completo, com nomes, números e figuras (decisão do dono, 04/11/2026), menos o que não é conteúdo do deck
(docs/plano-github-plugin.md, seção d):
- os vídeos, as dependências do Node, os builds e as capturas que o QA refaz;
- os PDFs, zips e arquivos auxiliares que uma compilação gera;
- a ferramenta de publicação do Netlify, ligada ao site e à conta do dono;
- os GIFs (eles vão para o README);
- as linhas de docs/CONTEXT.md com caminhos desta máquina.
No fim, lista as linhas que ainda citam um caminho pessoal (para a varredura da etapa 8). Só a biblioteca padrão.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "plugin" / "plugins" / "deck-studio" / "templates" / "exemplo-nexus-go"
SKIP_DIRS = {"video", "video-pt", "node_modules", "__pycache__", ".git", "shots", "shots-pt", "dist", "build", "gifs",
             ".impeccable"}  # the last: a design tool's cache, not the deck's
AUX = (".aux", ".log", ".nav", ".snm", ".toc", ".out", ".fls", ".fdb_latexmk", ".synctex.gz", ".bbl", ".blg", ".vrb",
       ".xdv", ".bcf", ".run.xml", ".zip")
SKIP_FILES = {"netlify-site.json", "publish_netlify.ps1"}
PERSONAL = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!voce\b)\w+|/c/Users/(?!voce\b)\w+|OneDrive[\\/]", re.I)
USER = re.compile(r"([A-Za-z]:[\\/]+Users[\\/]+|/c/Users/)(?!voce\b)\w+")  # a user folder in an example path
TEXT = {".md", ".tex", ".html", ".js", ".mjs", ".css", ".json", ".py", ".txt", ".bib", ".cls", ".sty", ".ps1", ".cmd"}


def kept(kit, p):
    rel = p.relative_to(kit)
    if rel.parts[:3] == ("deck", "build", "svg"):  # the TikZ figures, rendered: the build reuses them without TeX
        return True
    if SKIP_DIRS & set(rel.parts[:-1]) or any(".backup-" in part for part in rel.parts):
        return False
    if p.name in SKIP_FILES or p.name.endswith(AUX):
        return False
    if p.suffix == ".pdf" and (p.with_suffix(".tex").is_file()  # a compile's output, or a -jobname one
                               or any(p.stem.startswith(t.stem + "-") for t in p.parent.glob("*.tex"))):
        return False
    if rel.parts[0] == "qa" and p.suffix == ".png":  # the QA's renders: it makes them again
        return False
    return True


def main(kit):
    kit = Path(kit).resolve()
    if not (kit / "deck" / "build.mjs").is_file():
        sys.exit(f"{kit} não é o kit do deck (falta deck/build.mjs)")
    if OUT.exists():
        shutil.rmtree(OUT)
    files = sorted(p for p in kit.rglob("*") if p.is_file() and kept(kit, p))
    for p in files:
        target = OUT / p.relative_to(kit)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    context = OUT / "docs" / "CONTEXT.md"
    if context.is_file():  # the table of this machine's folders goes; the rest of the page stays
        lines = context.read_text(encoding="utf-8").split("\n")
        context.write_text("\n".join(ln for ln in lines if not PERSONAL.search(ln)), encoding="utf-8")
    for p in OUT.rglob("*"):  # what is left of this machine's user folder, in prose: the example user
        if p.is_file() and p.suffix.lower() in TEXT and p != context:
            text = p.read_text(encoding="utf-8", errors="surrogateescape")
            if USER.search(text):
                p.write_text(USER.sub(lambda m: m[1] + "voce", text), encoding="utf-8", errors="surrogateescape")
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"exemplo: {len(files)} arquivos, {size / 2**20:.1f} MB em {OUT.relative_to(ROOT).as_posix()}")
    left = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT:
            for i, ln in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
                if PERSONAL.search(ln):
                    left.append(f"{p.relative_to(OUT).as_posix()}:{i}: {ln.strip()[:120]}")
    print(f"linhas com caminho pessoal: {len(left)}")
    for ln in left:
        print("  " + ln)


if __name__ == "__main__":
    main(sys.argv[1])
