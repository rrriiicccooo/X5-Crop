#include "x5crop_native/ScanModels.h"

namespace x5crop {

QString statusLabel(const ScanStatus status)
{
    switch (status) {
    case ScanStatus::NotAnalyzed:
        return "Not analyzed";
    case ScanStatus::Analyzing:
        return "Analyzing";
    case ScanStatus::NeedsReview:
        return "Needs review";
    case ScanStatus::Approved:
        return "Approved";
    case ScanStatus::Locked:
        return "Locked";
    case ScanStatus::Exported:
        return "Exported";
    case ScanStatus::Failed:
        return "Failed";
    }
    return "Unknown";
}

QColor statusColor(const ScanStatus status)
{
    switch (status) {
    case ScanStatus::NotAnalyzed:
        return QColor("#737373");
    case ScanStatus::Analyzing:
        return QColor("#4ea1ff");
    case ScanStatus::NeedsReview:
        return QColor("#d29922");
    case ScanStatus::Approved:
        return QColor("#3fb950");
    case ScanStatus::Locked:
        return QColor("#bc8cff");
    case ScanStatus::Exported:
        return QColor("#58a6ff");
    case ScanStatus::Failed:
        return QColor("#f85149");
    }
    return QColor("#737373");
}

} // namespace x5crop

