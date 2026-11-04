"""A project made from a folder with several PDFs: its CLAUDE.md names every PDF and its real extraction folder
(the tutorial take of 2026-11-04 found the template pointing at one PDF and at a folder that did not exist)."""
from deck_studio import projects


def test_claude_md_names_every_pdf_and_its_extraction_folder(tmp_path):
    files = {"papers/a.pdf": b"%PDF-1.4", "papers/b.pdf": b"%PDF-1.4", "notes/n.md": b"x"}
    projects.create_from_files(tmp_path / "p", "Seminario", "seminario", "html", "en", files, "papers/a.pdf")
    projects.point_to_sources(tmp_path / "p", "seminario", {"papers/a.pdf": "a", "papers/b.pdf": "b"})
    text = (tmp_path / "p" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "comes from the imported PDFs (`context/papers/a.pdf`, `context/papers/b.pdf`)" in text
    assert "`context/a/` (from `papers/a.pdf`), `context/b/` (from `papers/b.pdf`)" in text
    assert "context/seminario/" not in text and "seminario/figuras" not in text
    assert "a/figuras/p012-1.png" in text


def test_one_pdf_keeps_the_template_text(tmp_path):
    projects.create_from_files(tmp_path / "p", "Um", "um", "html", "pt", {"a.pdf": b"%PDF-1.4"}, "a.pdf")
    before = (tmp_path / "p" / "CLAUDE.md").read_text(encoding="utf-8")
    projects.point_to_sources(tmp_path / "p", "um", {"a.pdf": "um"})
    assert (tmp_path / "p" / "CLAUDE.md").read_text(encoding="utf-8") == before
    assert "context/um/" in before
