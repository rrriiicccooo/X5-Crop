#include "x5crop_native/MainWindow.h"

#include <QApplication>
#include <QButtonGroup>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QSplitter>
#include <QStatusBar>
#include <QVBoxLayout>

namespace x5crop {

namespace {

constexpr auto kStyleSheet = R"(
QMainWindow, QWidget {
    background: #171717;
    color: #f2f2f2;
    font-size: 12px;
}
QFrame#topBar, QFrame#leftPanel, QFrame#centerPanel, QFrame#exportPage, QTabWidget::pane {
    background: #202020;
    border: 1px solid #343434;
}
QPushButton {
    background: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    padding: 6px 10px;
}
QPushButton:hover {
    background: #333333;
}
QPushButton:checked, QPushButton#primaryButton {
    background: #1f5f99;
    border-color: #4ea1ff;
}
QListWidget {
    background: #1c1c1c;
    border: 1px solid #343434;
    outline: none;
}
QListWidget::item {
    padding: 6px;
}
QListWidget::item:selected {
    background: #26384c;
}
QTabBar::tab {
    background: #242424;
    border: 1px solid #343434;
    padding: 7px 10px;
}
QTabBar::tab:selected {
    background: #303030;
    border-bottom-color: #4ea1ff;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #111111;
    border: 1px solid #343434;
    border-radius: 4px;
    padding: 5px;
}
QLabel#mutedLabel {
    color: #a8a8a8;
}
)";

bool isTiff(const QString& path)
{
    const QString suffix = QFileInfo(path).suffix().toLower();
    return suffix == "tif" || suffix == "tiff";
}

} // namespace

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("X5 Crop Native Review Workspace");
    resize(1440, 920);
    qApp->setStyleSheet(kStyleSheet);
    buildUi();
    refreshAll();
}

void MainWindow::buildUi()
{
    auto* root = new QWidget(this);
    auto* rootLayout = new QVBoxLayout(root);
    rootLayout->setContentsMargins(10, 10, 10, 10);
    rootLayout->setSpacing(8);
    setCentralWidget(root);

    buildTopBar(root);
    rootLayout->addWidget(root->findChild<QFrame*>("topBar"));

    auto* body = new QSplitter(Qt::Horizontal, root);
    body->setChildrenCollapsible(false);
    body->addWidget(buildLeftPanel());
    body->addWidget(buildCenterPanel());
    m_inspector = new InspectorPanel(body);
    m_inspector->setMinimumWidth(320);
    body->addWidget(m_inspector);
    body->setSizes({260, 860, 340});
    rootLayout->addWidget(body, 1);

    m_filmstrip = new FilmstripWidget(root);
    m_filmstrip->setMinimumHeight(132);
    m_filmstrip->setMaximumHeight(150);
    rootLayout->addWidget(m_filmstrip);

    connect(m_filmstrip, &FilmstripWidget::scanActivated, this, &MainWindow::selectScan);
    connect(m_inspector, &InspectorPanel::exportApprovedRequested, this, &MainWindow::exportApproved);

    statusBar()->showMessage("Ready");
}

void MainWindow::buildTopBar(QWidget* parent)
{
    auto* bar = new QFrame(parent);
    bar->setObjectName("topBar");
    auto* layout = new QHBoxLayout(bar);
    layout->setContentsMargins(10, 8, 10, 8);
    layout->setSpacing(8);

    auto* modes = new QButtonGroup(bar);
    modes->setExclusive(true);

    m_libraryMode = new QPushButton("Library", bar);
    m_reviewMode = new QPushButton("Review", bar);
    m_exportMode = new QPushButton("Export", bar);
    for (auto* button : {m_libraryMode, m_reviewMode, m_exportMode}) {
        button->setCheckable(true);
        modes->addButton(button);
        layout->addWidget(button);
    }
    m_reviewMode->setChecked(true);

    connect(m_libraryMode, &QPushButton::clicked, this, &MainWindow::setModeLibrary);
    connect(m_reviewMode, &QPushButton::clicked, this, &MainWindow::setModeReview);
    connect(m_exportMode, &QPushButton::clicked, this, &MainWindow::setModeExport);

    layout->addSpacing(18);
    auto* addFile = new QPushButton("Add File", bar);
    auto* addFolder = new QPushButton("Add Folder", bar);
    auto* output = new QPushButton("Output Folder", bar);
    connect(addFile, &QPushButton::clicked, this, &MainWindow::addFiles);
    connect(addFolder, &QPushButton::clicked, this, &MainWindow::addFolder);
    connect(output, &QPushButton::clicked, this, &MainWindow::chooseOutputFolder);
    layout->addWidget(addFile);
    layout->addWidget(addFolder);
    layout->addWidget(output);

    layout->addStretch(1);

    auto* analyze = new QPushButton("Analyze", bar);
    auto* reanalyze = new QPushButton("Reanalyze", bar);
    auto* approve = new QPushButton("Approve", bar);
    auto* exportButton = new QPushButton("Export", bar);
    analyze->setObjectName("primaryButton");
    connect(analyze, &QPushButton::clicked, this, &MainWindow::analyzeBatch);
    connect(approve, &QPushButton::clicked, this, &MainWindow::approveCurrent);
    connect(exportButton, &QPushButton::clicked, this, &MainWindow::exportApproved);
    layout->addWidget(analyze);
    layout->addWidget(reanalyze);
    layout->addWidget(approve);
    layout->addWidget(exportButton);
}

QWidget* MainWindow::buildLeftPanel()
{
    auto* panel = new QFrame(this);
    panel->setObjectName("leftPanel");
    panel->setMinimumWidth(240);
    auto* layout = new QVBoxLayout(panel);

    auto* title = new QLabel("Library", panel);
    title->setStyleSheet("font-size: 16px; font-weight: 600;");
    layout->addWidget(title);

    m_batchSummary = new QLabel(panel);
    m_batchSummary->setObjectName("mutedLabel");
    m_batchSummary->setWordWrap(true);
    layout->addWidget(m_batchSummary);

    auto* groups = new QListWidget(panel);
    groups->addItems({"All", "Not analyzed", "Needs review", "Approved", "Exported", "Failed"});
    groups->setMaximumHeight(164);
    groups->setCurrentRow(0);
    layout->addWidget(groups);

    auto* queueLabel = new QLabel("Batch queue", panel);
    queueLabel->setStyleSheet("font-weight: 600;");
    layout->addWidget(queueLabel);

    m_queue = new QListWidget(panel);
    layout->addWidget(m_queue, 1);
    connect(m_queue, &QListWidget::currentRowChanged, this, &MainWindow::selectScan);

    auto* remove = new QPushButton("Remove Selected", panel);
    connect(remove, &QPushButton::clicked, this, &MainWindow::removeSelected);
    layout->addWidget(remove);
    return panel;
}

QWidget* MainWindow::buildCenterPanel()
{
    auto* panel = new QFrame(this);
    panel->setObjectName("centerPanel");
    auto* layout = new QVBoxLayout(panel);
    layout->setContentsMargins(0, 0, 0, 0);

    m_centerStack = new QStackedWidget(panel);
    m_canvas = new ReviewCanvas(m_centerStack);
    m_centerStack->addWidget(m_canvas);
    m_centerStack->addWidget(buildExportSummary());
    layout->addWidget(m_centerStack, 1);

    auto* canvasTools = new QFrame(panel);
    auto* toolLayout = new QHBoxLayout(canvasTools);
    toolLayout->setContentsMargins(10, 8, 10, 8);
    auto* fit = new QPushButton("Zoom to Fit", canvasTools);
    auto* one = new QPushButton("100%", canvasTools);
    auto* crop = new QPushButton("Crop Boxes", canvasTools);
    auto* lines = new QPushButton("Split Lines", canvasTools);
    auto* grid = new QPushButton("Grid", canvasTools);
    for (auto* toggle : {crop, lines, grid}) {
        toggle->setCheckable(true);
        toggle->setChecked(true);
    }
    connect(fit, &QPushButton::clicked, m_canvas, &ReviewCanvas::zoomToFit);
    connect(one, &QPushButton::clicked, m_canvas, [this] { m_canvas->setZoomPercent(100); });
    connect(crop, &QPushButton::toggled, m_canvas, &ReviewCanvas::setShowCropBoxes);
    connect(lines, &QPushButton::toggled, m_canvas, &ReviewCanvas::setShowSplitLines);
    connect(grid, &QPushButton::toggled, m_canvas, &ReviewCanvas::setShowGrid);
    toolLayout->addWidget(fit);
    toolLayout->addWidget(one);
    toolLayout->addStretch(1);
    toolLayout->addWidget(crop);
    toolLayout->addWidget(lines);
    toolLayout->addWidget(grid);
    layout->addWidget(canvasTools);
    return panel;
}

QWidget* MainWindow::buildExportSummary()
{
    auto* page = new QFrame(this);
    page->setObjectName("exportPage");
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(40, 40, 40, 40);
    auto* title = new QLabel("Export Summary", page);
    title->setStyleSheet("font-size: 22px; font-weight: 650;");
    layout->addWidget(title);
    m_exportSummary = new QLabel(page);
    m_exportSummary->setWordWrap(true);
    layout->addWidget(m_exportSummary);
    layout->addStretch(1);
    return page;
}

void MainWindow::addFiles()
{
    const auto files = QFileDialog::getOpenFileNames(this, "Add TIFF scans", QString(), "TIFF scans (*.tif *.tiff)");
    for (const auto& file : files) {
        addScanPath(file);
    }
    refreshAll();
}

void MainWindow::addFolder()
{
    const QString folder = QFileDialog::getExistingDirectory(this, "Add TIFF folder");
    if (folder.isEmpty()) {
        return;
    }
    const QDir dir(folder);
    const auto files = dir.entryInfoList({"*.tif", "*.tiff", "*.TIF", "*.TIFF"}, QDir::Files, QDir::Name);
    for (const auto& info : files) {
        addScanPath(info.absoluteFilePath());
    }
    refreshAll();
}

void MainWindow::removeSelected()
{
    const int row = currentRow();
    if (row >= 0 && row < m_scans.size()) {
        m_scans.removeAt(row);
        refreshAll();
    }
}

void MainWindow::chooseOutputFolder()
{
    const QString folder = QFileDialog::getExistingDirectory(this, "Choose output folder", m_outputFolder);
    if (!folder.isEmpty()) {
        m_outputFolder = folder;
        m_inspector->setOutputFolder(folder);
        refreshSummary();
    }
}

void MainWindow::setModeLibrary()
{
    m_centerStack->setCurrentIndex(0);
    statusBar()->showMessage("Library mode");
}

void MainWindow::setModeReview()
{
    m_centerStack->setCurrentIndex(0);
    statusBar()->showMessage("Review mode");
}

void MainWindow::setModeExport()
{
    m_centerStack->setCurrentIndex(1);
    refreshSummary();
    statusBar()->showMessage("Export mode");
}

void MainWindow::selectScan(const int row)
{
    if (row >= 0 && row < m_scans.size()) {
        if (m_queue->currentRow() != row) {
            m_queue->setCurrentRow(row);
        }
        m_filmstrip->setCurrentScan(row);
        m_canvas->setScan(&m_scans[row]);
        m_inspector->setScan(&m_scans[row]);
    } else {
        m_canvas->setScan(nullptr);
        m_inspector->setScan(nullptr);
    }
}

void MainWindow::analyzeBatch()
{
    for (auto& scan : m_scans) {
        if (scan.plan.status == ScanStatus::NotAnalyzed) {
            scan.plan.status = ScanStatus::NeedsReview;
            scan.plan.confidencePercent = 72;
            scan.plan.warnings = {"engine_bridge_pending"};
        }
    }
    refreshAll();
    statusBar()->showMessage("Native shell marked scans as needs review; Python engine bridge is next.");
}

void MainWindow::approveCurrent()
{
    const int row = currentRow();
    if (row >= 0 && row < m_scans.size()) {
        m_scans[row].plan.status = ScanStatus::Approved;
        m_scans[row].plan.confidencePercent = std::max(m_scans[row].plan.confidencePercent, 90);
        m_scans[row].plan.warnings.clear();
        refreshAll();
        selectScan(row);
    }
}

void MainWindow::exportApproved()
{
    const int approved = std::count_if(m_scans.cbegin(), m_scans.cend(), [](const ScanItem& scan) {
        return scan.plan.status == ScanStatus::Approved || scan.plan.status == ScanStatus::Locked;
    });
    QMessageBox::information(this, "Export", QString("Export bridge pending.\nApproved scans ready: %1").arg(approved));
}

void MainWindow::refreshAll()
{
    refreshQueue();
    m_filmstrip->setScans(m_scans);
    refreshSummary();
    const int lastRow = static_cast<int>(m_scans.size()) - 1;
    selectScan(m_scans.isEmpty() ? -1 : std::clamp(currentRow(), 0, lastRow));
}

void MainWindow::refreshQueue()
{
    m_queue->clear();
    for (const auto& scan : m_scans) {
        auto* item = new QListWidgetItem(QString("%1\n%2").arg(scan.displayName, statusLabel(scan.plan.status)));
        item->setForeground(statusColor(scan.plan.status));
        m_queue->addItem(item);
    }
}

void MainWindow::refreshSummary()
{
    int needsReview = 0;
    int approved = 0;
    int exported = 0;
    int failed = 0;
    for (const auto& scan : m_scans) {
        needsReview += scan.plan.status == ScanStatus::NeedsReview ? 1 : 0;
        approved += scan.plan.status == ScanStatus::Approved || scan.plan.status == ScanStatus::Locked ? 1 : 0;
        exported += scan.plan.status == ScanStatus::Exported ? 1 : 0;
        failed += scan.plan.status == ScanStatus::Failed ? 1 : 0;
    }
    m_batchSummary->setText(QString("%1 scans\n%2 approved\n%3 need review\n%4 exported\n%5 failed")
                                .arg(m_scans.size())
                                .arg(approved)
                                .arg(needsReview)
                                .arg(exported)
                                .arg(failed));
    if (m_exportSummary != nullptr) {
        m_exportSummary->setText(QString("%1 scans in batch\n%2 approved or locked\n%3 blocked until review\n\nOutput folder:\n%4")
                                     .arg(m_scans.size())
                                     .arg(approved)
                                     .arg(m_scans.size() - approved)
                                     .arg(m_outputFolder.isEmpty() ? "(not selected)" : m_outputFolder));
    }
}

void MainWindow::addScanPath(const QString& path)
{
    if (!isTiff(path)) {
        return;
    }
    const QString absolute = QFileInfo(path).absoluteFilePath();
    const auto exists = std::any_of(m_scans.cbegin(), m_scans.cend(), [&](const ScanItem& item) {
        return item.sourcePath == absolute;
    });
    if (!exists) {
        m_scans.append(makeScanItem(absolute));
    }
}

ScanItem MainWindow::makeScanItem(const QString& path) const
{
    const QFileInfo info(path);
    ScanItem item;
    item.sourcePath = info.absoluteFilePath();
    item.displayName = info.fileName();
    item.plan.sourcePath = item.sourcePath;
    item.plan.outputDir = m_outputFolder;
    item.plan.status = ScanStatus::NotAnalyzed;
    item.plan.frameCount = 6;
    item.plan.bleed = 10;
    return item;
}

int MainWindow::currentRow() const
{
    return m_queue != nullptr ? m_queue->currentRow() : -1;
}

} // namespace x5crop
