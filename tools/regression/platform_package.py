"""Build the non-release Intel macOS validation transfer bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Sequence
import zipfile

from .platform_io import load_platform_sources
from .platform_receipt import PROJECT_ROOT, clean_commit
from .file_identity import sha256_file


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "build" / "v5-intel-validation"


def build_intel_validation_package(output_root: Path) -> Path:
    commit = clean_commit()
    if subprocess.run(
        ("git", "branch", "--show-current"),
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip() != "main":
        raise ValueError("Intel validation package must be built from main")
    output_root.mkdir(parents=True, exist_ok=True)
    archive = output_root / f"X5-Crop-V5-Intel-validation-{commit[:12]}.zip"
    with TemporaryDirectory(prefix="x5crop-intel-package-") as temporary:
        root = Path(temporary) / "X5-Crop-V5-Intel-validation"
        root.mkdir()
        bundle = root / "X5-Crop-V5.bundle"
        subprocess.run(
            ("git", "bundle", "create", str(bundle), "main"),
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        command = root / "X5_Crop_Intel_validate.command"
        shutil.copy2(
            PROJECT_ROOT / "tools/platform/X5_Crop_Intel_validate.command",
            command,
        )
        command.chmod(0o755)
        (root / "X5_Crop_Intel_expected_commit.txt").write_text(
            commit + "\n", encoding="utf-8"
        )
        sources = load_platform_sources(verify_files=False)
        (root / "required-sources.json").write_text(
            json.dumps(
                {
                    "schema": "x5crop_intel_required_sources_v1",
                    "git_commit": commit,
                    "sources": [
                        {
                            "sample_id": source.sample_id,
                            "source_relative_path": source.source_path.relative_to(
                                PROJECT_ROOT
                            ).as_posix(),
                            "source_sha256": source.source_sha256,
                        }
                        for source in sources
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "操作说明.txt").write_text(
            (
                "X5 Crop V5 Intel macOS 开发验证包（不是 RC 或用户发布包）\n\n"
                "1. 在本目录执行：git clone X5-Crop-V5.bundle X5-Crop\n"
                "2. 按 required-sources.json 把六张 SHA 匹配的 TIFF 放入 "
                "X5-Crop/Test/ 对应路径。\n"
                "3. 双击 X5_Crop_Intel_validate.command。\n"
                "4. 命令只接受 x86_64、干净工作树和 expected commit，并转调唯一 "
                "tools/verify platform。\n\n"
                "验证合同与 receipt 说明的唯一详细 owner："
                "克隆后的 X5-Crop/docs/ARCHITECTURE.md。\n"
            ),
            encoding="utf-8",
        )
        checksum_targets = tuple(
            sorted(
                (path for path in root.iterdir() if path.name != "SHA256SUMS"),
                key=lambda path: path.name,
            )
        )
        (root / "SHA256SUMS").write_text(
            "".join(
                f"{sha256_file(path)}  {path.name}\n"
                for path in checksum_targets
            ),
            encoding="utf-8",
        )
        with zipfile.ZipFile(
            archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as output:
            for path in sorted(root.iterdir(), key=lambda item: item.name):
                output.write(path, f"{root.name}/{path.name}")
    return archive


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("intel-macos",))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    archive = build_intel_validation_package(args.output_root.resolve())
    print(f"Intel validation package: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
