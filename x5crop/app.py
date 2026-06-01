from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .core_bridge import (
    EngineOptions,
    analysis_preview_for,
    debug_preview_for,
    default_output_dir,
    discover_tiffs,
    read_report,
    run_engine,
)
from .storage import app_paths, ensure_app_dirs, load_settings, save_settings


class EngineWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(int, int, str)
    failed = Signal(str)

    def __init__(self, input_path: Path, output_dir: Optional[Path], options: EngineOptions, dry_run: bool) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.options = options
        self.dry_run = dry_run

    @Slot()
    def run(self) -> None:
        try:
            ok, fail, out_dir = run_engine(
                input_path=self.input_path,
                output_dir=self.output_dir,
                options=self.options,
                dry_run=self.dry_run,
                log_callback=self.log.emit,
                progress_callback=self.progress.emit,
            )
            self.finished.emit(ok, fail, str(out_dir))
        except Exception as exc:
            self.failed.emit(str(exc))


class PreviewLabel(QLabel):
    def __init__(self) -> None:
        super().__init__("暂无预览。先点击 Analyze 生成 debug 图。")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(480, 320))
        self.setStyleSheet("QLabel { background: #1f1f1f; color: #ddd; border: 1px solid #444; }")
        self._pixmap: Optional[QPixmap] = None

    def set_image(self, path: Path) -> None:
        if not path.exists():
            self._pixmap = None
            self.setText(f"预览不存在：\n{path}")
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            self._pixmap = None
            self.setText(f"无法读取预览：\n{path}")
            return
        self._pixmap = pix
        self._update_scaled()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_scaled()

    def _update_scaled(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_app_dirs()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1280, 820)

        self._settings = load_settings()
        self._files: list[Path] = []
        self._last_output_dir: Optional[Path] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[EngineWorker] = None

        self._build_ui()
        self._load_settings_to_ui()
        self._connect_signals()
        self._refresh_storage_tab()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_analyze = QAction("Analyze", self)
        act_analyze.triggered.connect(self.analyze)
        toolbar.addAction(act_analyze)
        self.act_analyze = act_analyze

        act_export = QAction("Export", self)
        act_export.triggered.connect(self.export)
        toolbar.addAction(act_export)
        self.act_export = act_export

        toolbar.addSeparator()
        act_open_output = QAction("Reveal Output", self)
        act_open_output.triggered.connect(self.reveal_output)
        toolbar.addAction(act_open_output)
        self.act_open_output = act_open_output

        act_clean = QAction("Reveal App Data", self)
        act_clean.triggered.connect(self.reveal_app_data)
        toolbar.addAction(act_clean)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        path_box = QGroupBox("Input / Output")
        path_layout = QGridLayout(path_box)
        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.btn_browse_file = QPushButton("File…")
        self.btn_browse_folder = QPushButton("Folder…")
        self.btn_browse_output = QPushButton("Output…")
        path_layout.addWidget(QLabel("Input"), 0, 0)
        path_layout.addWidget(self.input_edit, 0, 1)
        path_layout.addWidget(self.btn_browse_file, 0, 2)
        path_layout.addWidget(self.btn_browse_folder, 0, 3)
        path_layout.addWidget(QLabel("Output"), 1, 0)
        path_layout.addWidget(self.output_edit, 1, 1)
        path_layout.addWidget(self.btn_browse_output, 1, 2, 1, 2)
        root.addWidget(path_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list = QListWidget()
        left_layout.addWidget(QLabel("Files"))
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        preview_tabs = QTabWidget()
        self.preview_label = PreviewLabel()
        self.analysis_label = PreviewLabel()
        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setWidget(self.preview_label)
        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setWidget(self.analysis_label)
        preview_tabs.addTab(scroll1, "Debug Preview")
        preview_tabs.addTab(scroll2, "Analysis Preview")
        center_layout.addWidget(preview_tabs, 1)
        splitter.addWidget(center)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        options_box = QGroupBox("Options")
        form = QFormLayout(options_box)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["standard", "fast", "underexposed", "review"])
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 12)
        self.count_spin.setValue(6)
        self.bleed_spin = QSpinBox()
        self.bleed_spin.setRange(0, 200)
        self.bleed_spin.setValue(10)
        self.deskew_combo = QComboBox()
        self.deskew_combo.addItems(["auto", "off", "strict"])
        self.analysis_combo = QComboBox()
        self.analysis_combo.addItems(["auto", "off", "strict"])
        self.outer_x_combo = QComboBox()
        self.outer_x_combo.addItems(["auto", "bw", "white"])
        self.outer_refine_combo = QComboBox()
        self.outer_refine_combo.addItems(["auto", "off", "strict"])
        self.grid_fit_combo = QComboBox()
        self.grid_fit_combo.addItems(["auto", "off", "strict"])
        self.frame_size_combo = QComboBox()
        self.frame_size_combo.addItems(["auto", "off", "strict"])
        self.compression_combo = QComboBox()
        self.compression_combo.addItems(["same", "none", "lzw", "deflate", "zstd"])
        self.debug_check = QCheckBox("Debug JPG")
        self.debug_check.setChecked(True)
        self.analysis_debug_check = QCheckBox("Analysis JPG")
        self.report_check = QCheckBox("Report JSONL")
        self.report_check.setChecked(True)
        self.overwrite_check = QCheckBox("Overwrite outputs")
        self.equal_split_check = QCheckBox("Force equal split")
        form.addRow("Preset", self.preset_combo)
        form.addRow("Frame count", self.count_spin)
        form.addRow("Bleed px", self.bleed_spin)
        form.addRow("Deskew", self.deskew_combo)
        form.addRow("Analysis", self.analysis_combo)
        form.addRow("Outer X", self.outer_x_combo)
        form.addRow("Outer refine", self.outer_refine_combo)
        form.addRow("Grid fit", self.grid_fit_combo)
        form.addRow("Frame size", self.frame_size_combo)
        form.addRow("Compression", self.compression_combo)
        form.addRow(self.debug_check)
        form.addRow(self.analysis_debug_check)
        form.addRow(self.report_check)
        form.addRow(self.overwrite_check)
        form.addRow(self.equal_split_check)
        right_layout.addWidget(options_box)

        btn_row = QHBoxLayout()
        self.btn_analyze = QPushButton("Analyze / Dry Run")
        self.btn_export = QPushButton("Export TIFFs")
        btn_row.addWidget(self.btn_analyze)
        btn_row.addWidget(self.btn_export)
        right_layout.addLayout(btn_row)

        self.info_tabs = QTabWidget()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.storage_text = QTextEdit()
        self.storage_text.setReadOnly(True)
        self.info_tabs.addTab(self.log_text, "Log")
        self.info_tabs.addTab(self.report_text, "Report")
        self.info_tabs.addTab(self.storage_text, "Storage")
        right_layout.addWidget(self.info_tabs, 1)
        splitter.addWidget(right)
        splitter.setSizes([250, 670, 360])

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Ready")
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status_label)
        root.addLayout(progress_row)

        self.setStatusBar(QStatusBar())

    def _connect_signals(self) -> None:
        self.btn_browse_file.clicked.connect(self.browse_file)
        self.btn_browse_folder.clicked.connect(self.browse_folder)
        self.btn_browse_output.clicked.connect(self.browse_output)
        self.btn_analyze.clicked.connect(self.analyze)
        self.btn_export.clicked.connect(self.export)
        self.input_edit.editingFinished.connect(self.on_input_changed)
        self.file_list.currentItemChanged.connect(self.on_file_selected)

    # ------------------------------------------------------------- settings
    def _load_settings_to_ui(self) -> None:
        s = self._settings
        self.input_edit.setText(s.get("input", ""))
        self.output_edit.setText(s.get("output", ""))
        self.bleed_spin.setValue(int(s.get("bleed", 10)))
        self.preset_combo.setCurrentText(s.get("preset", "standard"))
        self.deskew_combo.setCurrentText(s.get("deskew", "auto"))
        self.analysis_combo.setCurrentText(s.get("analysis", "auto"))
        self.debug_check.setChecked(bool(s.get("debug", True)))
        self.analysis_debug_check.setChecked(bool(s.get("debug_analysis", False)))
        self.report_check.setChecked(bool(s.get("report", True)))
        if self.input_edit.text().strip():
            self.populate_file_list()

    def _save_ui_settings(self) -> None:
        data = {
            "input": self.input_edit.text().strip(),
            "output": self.output_edit.text().strip(),
            "bleed": self.bleed_spin.value(),
            "preset": self.preset_combo.currentText(),
            "deskew": self.deskew_combo.currentText(),
            "analysis": self.analysis_combo.currentText(),
            "debug": self.debug_check.isChecked(),
            "debug_analysis": self.analysis_debug_check.isChecked(),
            "report": self.report_check.isChecked(),
        }
        save_settings(data)
        self._settings = data
        self._refresh_storage_tab()

    # --------------------------------------------------------------- actions
    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose TIFF", self.input_edit.text() or str(Path.home()), "TIFF Files (*.tif *.tiff)")
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text().strip():
                self.output_edit.setText(str(default_output_dir(Path(path))))
            self.populate_file_list()
            self._save_ui_settings()

    def browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose TIFF Folder", self.input_edit.text() or str(Path.home()))
        if path:
            self.input_edit.setText(path)
            if not self.output_edit.text().strip():
                self.output_edit.setText(str(default_output_dir(Path(path))))
            self.populate_file_list()
            self._save_ui_settings()

    def browse_output(self) -> None:
        start = self.output_edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Choose Output Folder", start)
        if path:
            self.output_edit.setText(path)
            self._save_ui_settings()

    def on_input_changed(self) -> None:
        if self.input_edit.text().strip() and not self.output_edit.text().strip():
            self.output_edit.setText(str(default_output_dir(Path(self.input_edit.text().strip()))))
        self.populate_file_list()
        self._save_ui_settings()

    def populate_file_list(self) -> None:
        self.file_list.clear()
        path_text = self.input_edit.text().strip()
        if not path_text:
            return
        self._files = discover_tiffs(Path(path_text))
        for p in self._files:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.file_list.addItem(item)
        self.status_label.setText(f"Found {len(self._files)} TIFF file(s)")

    def options(self) -> EngineOptions:
        return EngineOptions(
            count=self.count_spin.value(),
            bleed=self.bleed_spin.value(),
            deskew=self.deskew_combo.currentText(),
            analysis_enhance=self.analysis_combo.currentText(),
            preset=self.preset_combo.currentText(),
            outer_x_detect=self.outer_x_combo.currentText(),
            outer_refine=self.outer_refine_combo.currentText(),
            grid_fit=self.grid_fit_combo.currentText(),
            frame_size_fit=self.frame_size_combo.currentText(),
            debug=self.debug_check.isChecked(),
            debug_analysis=self.analysis_debug_check.isChecked(),
            report=self.report_check.isChecked(),
            overwrite=self.overwrite_check.isChecked(),
            equal_split=self.equal_split_check.isChecked(),
            compression=self.compression_combo.currentText(),
        )

    def analyze(self) -> None:
        self.start_job(dry_run=True)

    def export(self) -> None:
        self.start_job(dry_run=False)

    def start_job(self, dry_run: bool) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "X5 Crop", "A job is already running.")
            return
        input_text = self.input_edit.text().strip()
        if not input_text:
            QMessageBox.warning(self, "X5 Crop", "Choose an input TIFF or folder first.")
            return
        self._save_ui_settings()
        input_path = Path(input_text).expanduser().resolve()
        output_dir = Path(self.output_edit.text().strip()).expanduser().resolve() if self.output_edit.text().strip() else None
        self.log_text.clear()
        self.report_text.clear()
        self.progress.setValue(0)
        self.status_label.setText("Running…")
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = EngineWorker(input_path, output_dir, self.options(), dry_run)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self.append_log)
        self._worker.progress.connect(self.update_progress)
        self._worker.finished.connect(self.job_finished)
        self._worker.failed.connect(self.job_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    @Slot(str)
    def append_log(self, line: str) -> None:
        self.log_text.append(line)

    @Slot(int, int, str)
    def update_progress(self, current: int, total: int, name: str) -> None:
        if total > 0:
            self.progress.setValue(int(current * 100 / total))
        self.status_label.setText(f"{current}/{total} {name}")

    @Slot(int, int, str)
    def job_finished(self, ok: int, fail: int, output_dir: str) -> None:
        self._last_output_dir = Path(output_dir)
        self.status_label.setText(f"Done: {ok} ok, {fail} failed")
        self.progress.setValue(100)
        self.load_report(Path(output_dir))
        if self.file_list.count() > 0 and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)
        else:
            self.on_file_selected(self.file_list.currentItem(), None)

    @Slot(str)
    def job_failed(self, message: str) -> None:
        self.status_label.setText("Failed")
        QMessageBox.critical(self, "X5 Crop", message)

    @Slot()
    def _cleanup_thread(self) -> None:
        self._set_running(False)
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def _set_running(self, running: bool) -> None:
        for widget in [self.btn_analyze, self.btn_export, self.act_analyze, self.act_export]:
            widget.setEnabled(not running)

    def output_dir_current(self) -> Optional[Path]:
        if self._last_output_dir is not None:
            return self._last_output_dir
        text = self.output_edit.text().strip()
        if text:
            return Path(text).expanduser().resolve()
        input_text = self.input_edit.text().strip()
        if input_text:
            return default_output_dir(Path(input_text))
        return None

    def on_file_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        source = Path(current.data(Qt.ItemDataRole.UserRole))
        out_dir = self.output_dir_current()
        if out_dir is None:
            return
        self.preview_label.set_image(debug_preview_for(out_dir, source))
        self.analysis_label.set_image(analysis_preview_for(out_dir, source))

    def load_report(self, output_dir: Path) -> None:
        rows = read_report(output_dir)
        if not rows:
            self.report_text.setPlainText("No split_report.jsonl found.")
            return
        lines: list[str] = []
        for row in rows:
            source = Path(row.get("source", "")).name
            warnings = row.get("warnings", []) or []
            gaps = row.get("gaps", []) or []
            methods = ", ".join(g.get("method", "?") for g in gaps)
            lines.append(f"{source}")
            lines.append(f"  gaps: {methods}")
            lines.append(f"  warnings: {len(warnings)}")
            for w in warnings[:5]:
                lines.append(f"    - {w}")
            if len(warnings) > 5:
                lines.append(f"    ... {len(warnings)-5} more")
            lines.append("")
        self.report_text.setPlainText("\n".join(lines))

    def reveal_output(self) -> None:
        out_dir = self.output_dir_current()
        if out_dir is None:
            return
        out_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def reveal_app_data(self) -> None:
        paths = ensure_app_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.config_dir)))

    def _refresh_storage_tab(self) -> None:
        paths = app_paths()
        text = (
            "X5 Crop uses traditional OS application-data folders.\n\n"
            f"Config: {paths.config_dir}\n"
            f"Cache:  {paths.cache_dir}\n"
            f"Logs:   {paths.log_dir}\n"
            f"Temp:   {paths.temp_dir}\n\n"
            "After uninstall, run the cleanup script in tools/ to remove these residual folders.\n"
            "Windows: tools\\cleanup_x5_crop_windows.ps1\n"
            "macOS:   tools/cleanup_x5_crop_macos.command\n"
        )
        self.storage_text.setPlainText(text)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._thread is not None:
            reply = QMessageBox.question(self, "X5 Crop", "A job is still running. Quit anyway?")
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._save_ui_settings()
        super().closeEvent(event)


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("X5 Crop")
    window = MainWindow()
    window.show()
    return app.exec()
