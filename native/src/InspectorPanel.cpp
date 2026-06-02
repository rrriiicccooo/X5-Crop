#include "x5crop_native/InspectorPanel.h"

#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QTextEdit>
#include <QVBoxLayout>

namespace x5crop {

InspectorPanel::InspectorPanel(QWidget* parent)
    : QTabWidget(parent)
{
    addTab(buildPlanTab(), "Plan");
    addTab(buildAdjustTab(), "Adjust");
    addTab(buildAnalyzeTab(), "Analyze");
    addTab(buildExportTab(), "Export");
}

void InspectorPanel::setScan(const ScanItem* item)
{
    if (item == nullptr) {
        m_statusValue->setText("No scan selected");
        m_confidenceValue->setText("-");
        m_confidenceBar->setValue(0);
        m_warningValue->setText("-");
        m_metadataValue->setText("-");
        m_methodValue->setText("-");
        return;
    }

    m_statusValue->setText(statusLabel(item->plan.status));
    m_confidenceValue->setText(QString("%1%").arg(item->plan.confidencePercent));
    m_confidenceBar->setValue(item->plan.confidencePercent);
    m_warningValue->setText(item->plan.warnings.isEmpty() ? "None" : item->plan.warnings.join(", "));
    m_metadataValue->setText(QString("Frames: %1\nBleed: %2 px").arg(item->plan.frameCount).arg(item->plan.bleed));
    m_methodValue->setText("Native UI shell; Python engine bridge pending");
    m_frameCount->setValue(item->plan.frameCount);
    m_bleed->setValue(item->plan.bleed);
}

void InspectorPanel::setOutputFolder(const QString& path)
{
    m_outputFolder->setText(path);
}

QWidget* InspectorPanel::buildPlanTab()
{
    auto* page = new QWidget(this);
    auto* form = new QFormLayout(page);
    form->setLabelAlignment(Qt::AlignLeft);

    m_statusValue = new QLabel("No scan selected", page);
    m_confidenceLabel = new QLabel("CONFIDENCE", page);
    m_confidenceValue = new QLabel("-", page);
    m_confidenceValue->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    m_confidenceBar = new QProgressBar(page);
    m_confidenceBar->setRange(0, 100);
    m_confidenceBar->setTextVisible(false);
    m_warningValue = new QLabel("-", page);
    m_warningValue->setWordWrap(true);
    m_metadataValue = new QLabel("-", page);
    m_metadataValue->setWordWrap(true);
    m_methodValue = new QLabel("-", page);
    m_methodValue->setWordWrap(true);

    form->addRow("Status", m_statusValue);
    auto* confidenceRow = new QWidget(page);
    auto* confidenceLayout = new QHBoxLayout(confidenceRow);
    confidenceLayout->setContentsMargins(0, 0, 0, 0);
    confidenceLayout->addWidget(m_confidenceLabel);
    confidenceLayout->addStretch(1);
    confidenceLayout->addWidget(m_confidenceValue);
    form->addRow(confidenceRow);
    form->addRow(m_confidenceBar);
    form->addRow("Warnings", m_warningValue);
    form->addRow("Metadata", m_metadataValue);
    form->addRow("Detection", m_methodValue);
    return page;
}

QWidget* InspectorPanel::buildAdjustTab()
{
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    auto* form = new QFormLayout();

    m_frameCount = new QSpinBox(page);
    m_frameCount->setRange(1, 12);
    m_frameCount->setValue(6);

    m_bleed = new QSpinBox(page);
    m_bleed->setRange(0, 200);
    m_bleed->setValue(10);

    auto* deskew = new QDoubleSpinBox(page);
    deskew->setRange(-10.0, 10.0);
    deskew->setDecimals(2);
    deskew->setSuffix(" deg");

    form->addRow("Frame count", m_frameCount);
    form->addRow("Bleed", m_bleed);
    form->addRow("Deskew", deskew);
    layout->addLayout(form);

    auto* resetLine = new QPushButton("Reset selected line", page);
    auto* resetAll = new QPushButton("Reset manual edits", page);
    auto* copyPrev = new QPushButton("Copy geometry from previous", page);
    auto* applySelected = new QPushButton("Apply geometry to selected", page);
    layout->addWidget(resetLine);
    layout->addWidget(resetAll);
    layout->addWidget(copyPrev);
    layout->addWidget(applySelected);
    layout->addStretch(1);
    return page;
}

QWidget* InspectorPanel::buildAnalyzeTab()
{
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    auto* form = new QFormLayout();

    m_preset = new QComboBox(page);
    m_preset->addItems({"Standard", "Fast", "Underexposed", "Review"});

    auto* deskew = new QComboBox(page);
    deskew->addItems({"auto", "off", "strict"});
    auto* enhance = new QComboBox(page);
    enhance->addItems({"auto", "off", "strict"});
    auto* refine = new QComboBox(page);
    refine->addItems({"auto", "off", "strict"});
    auto* grid = new QComboBox(page);
    grid->addItems({"auto", "off", "strict"});
    auto* frameSize = new QComboBox(page);
    frameSize->addItems({"auto", "off", "strict"});
    auto* equal = new QCheckBox("Force equal split", page);

    form->addRow("Preset", m_preset);
    form->addRow("Deskew", deskew);
    form->addRow("Analysis", enhance);
    form->addRow("Outer refine", refine);
    form->addRow("Grid fit", grid);
    form->addRow("Frame size", frameSize);
    form->addRow(equal);
    layout->addLayout(form);

    auto* current = new QPushButton("Reanalyze current", page);
    auto* selected = new QPushButton("Reanalyze selected", page);
    connect(current, &QPushButton::clicked, this, &InspectorPanel::reanalyzeCurrentRequested);
    connect(selected, &QPushButton::clicked, this, &InspectorPanel::reanalyzeSelectedRequested);
    layout->addWidget(current);
    layout->addWidget(selected);
    layout->addStretch(1);
    return page;
}

QWidget* InspectorPanel::buildExportTab()
{
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    auto* form = new QFormLayout();

    m_outputFolder = new QLineEdit(page);
    auto* compression = new QComboBox(page);
    compression->addItems({"same", "none", "lzw", "deflate", "zstd"});
    auto* overwrite = new QCheckBox("Overwrite outputs", page);

    form->addRow("Output", m_outputFolder);
    form->addRow("Compression", compression);
    form->addRow(overwrite);
    layout->addLayout(form);

    auto* note = new QLabel("Final export should use approved CropPlans and preserve TIFF metadata.", page);
    note->setWordWrap(true);
    note->setObjectName("mutedLabel");
    layout->addWidget(note);

    auto* approved = new QPushButton("Export approved", page);
    auto* selected = new QPushButton("Export selected", page);
    connect(approved, &QPushButton::clicked, this, &InspectorPanel::exportApprovedRequested);
    connect(selected, &QPushButton::clicked, this, &InspectorPanel::exportSelectedRequested);
    layout->addWidget(approved);
    layout->addWidget(selected);
    layout->addStretch(1);
    return page;
}

} // namespace x5crop
