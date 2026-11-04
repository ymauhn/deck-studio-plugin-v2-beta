"""beamer/overleaf.py: what the Overleaf zip takes from a deck's folder (no TeX needed)."""
import zipfile

from deck_studio.beamer import overleaf

TEX = r"""\documentclass{beamer}
\usetheme{Meu}
\usepackage{cores}
\graphicspath{{figures/}{logos/}}
% \input{comentado.tex} and \includegraphics{comentada} stay out
\begin{document}
\input{tables}
\include{partes/um}
\includegraphics[width=2cm]{grafico}\includegraphics{logo.pdf}
\bibliographystyle{meu}
\bibliography{refs,outra}
\end{document}
"""


def test_the_zip_takes_what_the_deck_reads_and_nothing_else(tmp_path):
    deck = tmp_path / "v2"
    for name, text in {"main.tex": TEX, "tables.tex": "a", "partes/um.tex": r"\input{partes/dois}",
                       "partes/dois.tex": "b", "refs.bib": "", "outra.bib": "", "meu.bst": "", "cores.sty": "",
                       "beamerthemeMeu.sty": "", "latexmkrc": "$pdf_mode = 1;", "LEIA-ME.md": "x",
                       "comentado.tex": "", "main.aux": "", "main.log": "", "solta.tex": ""}.items():
        (deck / name).parent.mkdir(parents=True, exist_ok=True)
        (deck / name).write_text(text, encoding="utf-8")
    for name in ("figures/grafico.png", "figures/grafico.pdf", "figures/comentada.png", "logos/logo.pdf"):
        (deck / name).parent.mkdir(parents=True, exist_ok=True)
        (deck / name).write_bytes(b"x")
    names = [f.relative_to(deck).as_posix() for f in overleaf.inputs(deck / "main.tex")]
    assert names[0] == "main.tex"
    assert sorted(names[1:]) == ["LEIA-ME.md", "beamerthemeMeu.sty", "cores.sty", "figures/grafico.pdf",
                                 "latexmkrc", "logos/logo.pdf", "meu.bst", "outra.bib", "partes/dois.tex",
                                 "partes/um.tex", "refs.bib", "tables.tex"]  # .pdf before .png, as pdfLaTeX looks
    (deck / "main.pdf").write_bytes(b"%PDF-1.5 last compile")
    z, zipped = overleaf.build(deck / "main.tex", deck / "main.pdf", tmp_path / "exports")
    assert z == tmp_path / "exports" / "main-overleaf.zip" and "main.pdf" in zipped
    with zipfile.ZipFile(z) as f:
        assert f.read("main.pdf") == b"%PDF-1.5 last compile"


def test_the_last_compiles_fls_adds_what_tex_read_inside_the_folder(tmp_path):
    deck, work = tmp_path / "d", tmp_path / "w"
    deck.mkdir()
    work.mkdir()
    (deck / "main.tex").write_text(r"\documentclass{beamer}\begin{document}\makeatletter\@input{gerado.tex}\end{document}",
                                   encoding="utf-8")
    (deck / "gerado.tex").write_text("x", encoding="utf-8")
    (work / "main.fls").write_text(f"PWD {deck}\nINPUT {deck / 'gerado.tex'}\nINPUT C:/texlive/beamer.cls\n"
                                   f"INPUT {work / 'main.aux'}\n", encoding="utf-8")
    names = [f.name for f in overleaf.inputs(deck / "main.tex", work)]
    assert names == ["main.tex", "gerado.tex"]
