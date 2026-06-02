#pragma once

#include <QLabel>
#include <QList>
#include <QListWidget>
#include <QMainWindow>
#include <QPushButton>
#include <QStackedWidget>

#include "x5crop_native/FilmstripWidget.h"
#include "x5crop_native/InspectorPanel.h"
#include "x5crop_native/ReviewCanvas.h"
#include "x5crop_native/ScanModels.h"

namespace x5crop {

class MainWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);

private slots:
    void addFiles();
    void addFolder();
    void removeSelected();
    void chooseOutputFolder();
    void setModeLibrary();
    void setModeReview();
    void setModeExport();
    void selectScan(int row);
    void analyzeBatch();
    void approveCurrent();
    void exportApproved();

private:
    void buildUi();
    void buildTopBar(QWidget* parent);
    QWidget* buildLeftPanel();
    QWidget* buildCenterPanel();
    QWidget* buildExportSummary();
    void refreshAll();
    void refreshQueue();
    void refreshSummary();
    void addScanPath(const QString& path);
    ScanItem makeScanItem(const QString& path) const;
    int currentRow() const;

    QList<ScanItem> m_scans;
    QString m_outputFolder;

    QListWidget* m_queue = nullptr;
    FilmstripWidget* m_filmstrip = nullptr;
    ReviewCanvas* m_canvas = nullptr;
    InspectorPanel* m_inspector = nullptr;
    QStackedWidget* m_centerStack = nullptr;
    QLabel* m_batchSummary = nullptr;
    QLabel* m_exportSummary = nullptr;
    QPushButton* m_libraryMode = nullptr;
    QPushButton* m_reviewMode = nullptr;
    QPushButton* m_exportMode = nullptr;
};

} // namespace x5crop

