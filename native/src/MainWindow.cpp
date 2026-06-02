#include "x5crop_native/MainWindow.h"

#include <QApplication>
#include <QButtonGroup>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHBoxLayout>
#include <QPainter>
#include <QPixmap>
#include <QLabel>
#include <QMenuBar>
#include <QMessageBox>
#include <QPushButton>
#include <QStatusBar>
#include <QToolButton>
#include <QVBoxLayout>

namespace x5crop {

namespace {

constexpr auto kStyleSheet = R"(
QMainWindow, QWidget {
    background: #eef2f7;
    color: #1f2937;
    font-size: 12px;
}
QToolBar {
    background: #fbfcfe;
    border: none;
    border-bottom: 1px solid #d8dee8;
    spacing: 6px;
}
QFrame#leftPanel, QFrame#exportPage, QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
}
QFrame#centerPanel {
    background: #ffffff;
    border: none;
    border-radius: 8px;
}
QPushButton {
    background: #f3f5f8;
    border: none;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover {
    background: #f7f9fc;
}
QPushButton:checked, QPushButton#primaryButton {
    color: #ffffff;
    background: #3d6fb6;
    border-color: #3d6fb6;
}
QListWidget {
    background: #ffffff;
    border: none;
    border-radius: 8px;
    outline: none;
}
QListWidget::item {
    padding: 8px;
    border-radius: 8px;
}
QListWidget::item:selected {
    color: #1f2937;
    background: #dbe8fb;
}
QListWidget#filmstrip {
    background: #f7f9fc;
    border: none;
    border-top: 1px solid #d8dee8;
    border-radius: 0;
}
QListWidget#filmstrip::item:selected {
    background: #ffffff;
    border-top: 3px solid #3d6fb6;
}
QTabBar::tab {
    background: #eceff4;
    border: none;
    padding: 7px 10px;
}
QTabBar::tab:selected {
    background: #ffffff;
    border-bottom-color: #3d6fb6;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 4px;
    padding: 5px;
}
QLabel#mutedLabel {
    color: #667085;
}
QLabel#sectionLabel {
    color: #98a2b3;
    font-size: 11px;
    font-weight: 700;
}
QLabel#warningCard {
    color: #1f2937;
    background: #fff4dc;
    border-radius: 10px;
    padding: 12px;
}
QLabel#sourceCard {
    background: #ffffff;
    border-radius: 9px;
    padding: 10px 12px;
}
QLabel#mutedMetric {
    color: #667085;
}
QProgressBar {
    background: #eef2f7;
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar::chunk {
    background: #7f93b6;
    border-radius: 4px;
}
)";

bool isTiff(const QString& path)
{
    const QString suffix = QFileInfo(path).suffix().toLower();
    return suffix == "tif" || suffix == "tiff";
}

QIcon queueIcon(const ScanStatus status)
{
    QPixmap pixmap(48, 28);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    QLinearGradient gradient(0, 0, 48, 0);
    gradient.setColorAt(0.0, QColor("#cfd7e3"));
    gradient.setColorAt(0.5, QColor("#eef2f7"));
    gradient.setColorAt(1.0, QColor("#aeb9c9"));
    painter.setPen(Qt::NoPen);
    painter.setBrush(gradient);
    painter.drawRoundedRect(QRectF(0, 0, 48, 28), 4, 4);
    painter.setBrush(statusColor(status));
    painter.drawEllipse(QRectF(36, 4, 9, 9));
    if (status == ScanStatus::NeedsReview) {
        painter.setPen(Qt::white);
        painter.setFont(QFont(".AppleSystemUIFont", 7, QFont::DemiBold));
        painter.drawText(QRectF(36, 2, 9, 11), Qt::AlignCenter, "!");
    }
    return QIcon(pixmap);
}

} // namespace

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("X5 Crop Native Review Workspace");
    resize(1440, 920);
    qApp->setStyleSheet(kStyleSheet);
    setUnifiedTitleAndToolBarOnMac(true);
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

    buildToolbar();

    m_bodySplitter = new QSplitter(Qt::Horizontal, root);
    m_bodySplitter->setChildrenCollapsible(false);
    m_leftPanel = buildLeftPanel();
    m_bodySplitter->addWidget(m_leftPanel);
    m_bodySplitter->addWidget(buildCenterPanel());
    m_inspector = new InspectorPanel(m_bodySplitter);
    m_inspector->setMinimumWidth(320);
    m_bodySplitter->addWidget(m_inspector);
    m_bodySplitter->setSizes({260, 860, 340});
    rootLayout->addWidget(m_bodySplitter, 1);

    connect(m_inspector, &InspectorPanel::approveRequested, this, &MainWindow::approveCurrent);

    m_filmstrip = new FilmstripWidget(root);
    m_filmstrip->setMinimumHeight(132);
    m_filmstrip->setMaximumHeight(150);
    rootLayout->addWidget(m_filmstrip);

    connect(m_filmstrip, &FilmstripWidget::scanActivated, this, &MainWindow::selectScan);
    connect(m_inspector, &InspectorPanel::exportApprovedRequested, this, &MainWindow::exportApproved);

    statusBar()->showMessage("Ready");
}

void MainWindow::buildToolbar()
{
    auto* toolbar = new QToolBar("Main Toolbar", this);
    toolbar->setMovable(false);
    toolbar->setIconSize(QSize(18, 18));
    addToolBar(Qt::TopToolBarArea, toolbar);

    auto* sidebar = new QPushButton("Sidebar", toolbar);
    sidebar->setCheckable(true);
    sidebar->setChecked(true);
    connect(sidebar, &QPushButton::clicked, this, &MainWindow::toggleSidebar);
    toolbar->addWidget(sidebar);

    auto* title = new QLabel("X5 Crop", toolbar);
    title->setStyleSheet("font-size: 20px; font-weight: 700; color: #1f2937; padding-left: 14px; padding-right: 22px;");
    toolbar->addWidget(title);

    auto* modeWrap = new QWidget(toolbar);
    auto* layout = new QHBoxLayout(modeWrap);
    layout->setContentsMargins(6, 0, 6, 0);
    layout->setSpacing(4);

    auto* modes = new QButtonGroup(modeWrap);
    modes->setExclusive(true);

    m_libraryMode = new QPushButton("Library", modeWrap);
    m_reviewMode = new QPushButton("Review", modeWrap);
    m_exportMode = new QPushButton("Export", modeWrap);
    for (auto* button : {m_libraryMode, m_reviewMode, m_exportMode}) {
        button->setCheckable(true);
        modes->addButton(button);
        layout->addWidget(button);
    }
    m_reviewMode->setChecked(true);

    connect(m_libraryMode, &QPushButton::clicked, this, &MainWindow::setModeLibrary);
    connect(m_reviewMode, &QPushButton::clicked, this, &MainWindow::setModeReview);
    connect(m_exportMode, &QPushButton::clicked, this, &MainWindow::setModeExport);

    toolbar->addWidget(modeWrap);
    auto* spacer = new QWidget(toolbar);
    spacer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    toolbar->addWidget(spacer);

    auto* previous = new QPushButton("Previous", toolbar);
    auto* next = new QPushButton("Next", toolbar);
    auto* analyze = new QPushButton("Analyze", toolbar);
    auto* reanalyze = new QPushButton("Reanalyze", toolbar);
    auto* approve = new QPushButton("Approve", toolbar);
    auto* inspector = new QPushButton("Inspector", toolbar);
    auto* exportButton = new QPushButton("Export", toolbar);
    inspector->setCheckable(true);
    inspector->setChecked(true);
    analyze->setObjectName("primaryButton");
    approve->setObjectName("primaryButton");
    connect(previous, &QPushButton::clicked, this, &MainWindow::selectPrevious);
    connect(next, &QPushButton::clicked, this, &MainWindow::selectNext);
    connect(analyze, &QPushButton::clicked, this, &MainWindow::analyzeBatch);
    connect(approve, &QPushButton::clicked, this, &MainWindow::approveCurrent);
    connect(inspector, &QPushButton::clicked, this, &MainWindow::toggleInspector);
    connect(exportButton, &QPushButton::clicked, this, &MainWindow::exportApproved);
    toolbar->addWidget(previous);
    toolbar->addWidget(next);
    toolbar->addWidget(analyze);
    toolbar->addWidget(reanalyze);
    toolbar->addWidget(approve);
    toolbar->addWidget(inspector);
    toolbar->addWidget(exportButton);
}

QWidget* MainWindow::buildLeftPanel()
{
    auto* panel = new QFrame(this);
    panel->setObjectName("leftPanel");
    panel->setMinimumWidth(264);
    auto* layout = new QVBoxLayout(panel);
    layout->setContentsMargins(24, 22, 24, 18);
    layout->setSpacing(12);

    auto* sourceTitle = new QLabel("SOURCE", panel);
    sourceTitle->setObjectName("sectionLabel");
    layout->addWidget(sourceTitle);

    m_sourcePathLabel = new QLabel("/Photography/X5 Test", panel);
    m_sourcePathLabel->setObjectName("sourceCard");
    m_sourcePathLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    layout->addWidget(m_sourcePathLabel);

    auto* importRow = new QWidget(panel);
    auto* importLayout = new QHBoxLayout(importRow);
    importLayout->setContentsMargins(0, 0, 0, 0);
    auto* addFile = new QPushButton("File", importRow);
    auto* addFolder = new QPushButton("Folder", importRow);
    connect(addFile, &QPushButton::clicked, this, &MainWindow::addFiles);
    connect(addFolder, &QPushButton::clicked, this, &MainWindow::addFolder);
    importLayout->addWidget(addFile);
    importLayout->addWidget(addFolder);
    layout->addWidget(importRow);

    layout->addSpacing(18);
    auto* batchTitle = new QLabel("BATCH", panel);
    batchTitle->setObjectName("sectionLabel");
    layout->addWidget(batchTitle);

    m_groups = new QListWidget(panel);
    m_groups->setMaximumHeight(206);
    m_groups->setCurrentRow(0);
    layout->addWidget(m_groups);

    layout->addSpacing(18);
    auto* queueLabel = new QLabel("QUEUE", panel);
    queueLabel->setObjectName("sectionLabel");
    layout->addWidget(queueLabel);

    m_queue = new QListWidget(panel);
    m_queue->setIconSize(QSize(48, 28));
    layout->addWidget(m_queue, 1);
    connect(m_queue, &QListWidget::currentRowChanged, this, &MainWindow::selectScan);

    auto* remove = new QPushButton("Remove Selected", panel);
    connect(remove, &QPushButton::clicked, this, &MainWindow::removeSelected);
    layout->addWidget(remove);
    return panel;
}

void MainWindow::toggleSidebar()
{
    if (m_leftPanel != nullptr) {
        m_leftPanel->setVisible(!m_leftPanel->isVisible());
    }
}

void MainWindow::toggleInspector()
{
    if (m_inspector != nullptr) {
        m_inspector->setVisible(!m_inspector->isVisible());
    }
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
    canvasTools->setVisible(false);
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
        m_sourcePathLabel->setText(sourceLabel());
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
            scan.plan.confidencePercent = 56;
            scan.plan.warnings = {"Weak separator near frame 3", "Frame width variance is high"};
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

void MainWindow::selectPrevious()
{
    const int row = currentRow();
    if (row > 0) {
        selectScan(row - 1);
    }
}

void MainWindow::selectNext()
{
    const int row = currentRow();
    if (row >= 0 && row + 1 < m_scans.size()) {
        selectScan(row + 1);
    }
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
        const QString detail = scan.plan.warnings.isEmpty()
            ? QString("%1% · %2").arg(scan.plan.confidencePercent).arg(statusLabel(scan.plan.status).toLower())
            : QString("%1% · %2").arg(scan.plan.confidencePercent).arg(scan.plan.warnings.first());
        auto* item = new QListWidgetItem(queueIcon(scan.plan.status), QString("%1\n%2").arg(scan.displayName, detail));
        item->setForeground(QColor("#1f2937"));
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
    if (m_groups != nullptr) {
        m_groups->clear();
        m_groups->addItem(QString("All scans                                      %1").arg(m_scans.size()));
        m_groups->addItem(QString("Needs review                              %1").arg(needsReview));
        m_groups->addItem(QString("Approved                                  %1").arg(approved));
        m_groups->addItem(QString("Exported                                  %1").arg(exported));
        m_groups->addItem(QString("Failed                                    %1").arg(failed));
        m_groups->setCurrentRow(0);
    }
    if (m_sourcePathLabel != nullptr) {
        m_sourcePathLabel->setText(sourceLabel());
    }
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
    item.plan.confidencePercent = 0;
    item.plan.frameCount = 6;
    item.plan.bleed = 10;
    return item;
}

int MainWindow::currentRow() const
{
    return m_queue != nullptr ? m_queue->currentRow() : -1;
}

QString MainWindow::sourceLabel() const
{
    if (!m_scans.isEmpty()) {
        return QFileInfo(m_scans.first().sourcePath).absolutePath();
    }
    if (!m_outputFolder.isEmpty()) {
        return m_outputFolder;
    }
    return "/Photography/X5 Test";
}

} // namespace x5crop
