#pragma once

#include <QCheckBox>
#include <QComboBox>
#include <QLabel>
#include <QLineEdit>
#include <QSpinBox>
#include <QTabWidget>

#include "x5crop_native/ScanModels.h"

namespace x5crop {

class InspectorPanel final : public QTabWidget {
    Q_OBJECT

public:
    explicit InspectorPanel(QWidget* parent = nullptr);

    void setScan(const ScanItem* item);
    void setOutputFolder(const QString& path);

signals:
    void reanalyzeCurrentRequested();
    void reanalyzeSelectedRequested();
    void exportApprovedRequested();
    void exportSelectedRequested();

private:
    QWidget* buildPlanTab();
    QWidget* buildAdjustTab();
    QWidget* buildAnalyzeTab();
    QWidget* buildExportTab();

    QLabel* m_statusValue = nullptr;
    QLabel* m_confidenceValue = nullptr;
    QLabel* m_warningValue = nullptr;
    QLabel* m_metadataValue = nullptr;
    QLabel* m_methodValue = nullptr;
    QLineEdit* m_outputFolder = nullptr;
    QComboBox* m_preset = nullptr;
    QSpinBox* m_frameCount = nullptr;
    QSpinBox* m_bleed = nullptr;
};

} // namespace x5crop

