#pragma once

#include <QColor>
#include <QList>
#include <QRect>
#include <QString>

namespace x5crop {

enum class ScanStatus {
    NotAnalyzed,
    Analyzing,
    NeedsReview,
    Approved,
    Locked,
    Exported,
    Failed,
};

struct CropPlan {
    QString sourcePath;
    QString outputDir;
    int frameCount = 6;
    double deskewAngle = 0.0;
    QRect outerBox;
    QList<int> boundaries;
    int bleed = 10;
    QList<QRect> cropBoxes;
    int confidencePercent = 0;
    ScanStatus status = ScanStatus::NotAnalyzed;
    QStringList warnings;
    bool manualOverrides = false;
    bool locked = false;
    QString analysisVersion = "native-ui-0.1.0";
};

struct ScanItem {
    QString sourcePath;
    QString displayName;
    QString previewPath;
    CropPlan plan;
};

QString statusLabel(ScanStatus status);
QColor statusColor(ScanStatus status);

} // namespace x5crop
