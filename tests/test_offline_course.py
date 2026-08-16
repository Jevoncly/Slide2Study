import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from slide2study.cli import main as cli_main
from slide2study.models import Page, RenderedPage


class _Parser:
    def parse(self, document: Path):
        return [
            Page(
                "deck-1",
                1,
                "Validation data: evidence used to select model hyperparameters.",
                title="Model Selection",
                metadata={"source_name": document.name},
            )
        ]


class OfflineCourseTests(unittest.TestCase):
    def test_one_command_builds_ready_to_open_site(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = root / "lecture.pdf"
            document.write_bytes(b"fake-pdf")
            output_dir = root / "course"

            def fake_render(source, rendered_dir, **_kwargs):
                image = Path(rendered_dir) / Path(source).stem / "page-0001.png"
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_bytes(b"fake-image")
                return [
                    RenderedPage(
                        "deck-1",
                        1,
                        str(image),
                        str(source),
                        1200,
                        900,
                        "sha",
                    )
                ]

            stdout = io.StringIO()
            with (
                patch("slide2study.cli.get_parser", return_value=_Parser()),
                patch("slide2study.cli.render_document", side_effect=fake_render),
                redirect_stdout(stdout),
            ):
                exit_code = cli_main(
                    [
                        "build-offline-course",
                        str(document),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            report = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(report["mode"], "offline-course")
            self.assertEqual(report["questions"], 1)
            self.assertTrue(Path(report["corpus"]).is_file())
            self.assertTrue(Path(report["manifest"]).is_file())
            self.assertTrue(Path(report["site"]).is_file())

    def test_rejects_non_renderable_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "notes.txt"
            document.write_text("notes", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supports only PDF/PPTX"):
                cli_main(
                    [
                        "build-offline-course",
                        str(document),
                        "--output-dir",
                        str(Path(directory) / "course"),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
