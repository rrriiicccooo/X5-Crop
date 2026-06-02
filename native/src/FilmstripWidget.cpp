#include "x5crop_native/FilmstripWidget.h"

#include <QPainter>
#include <QPixmap>

namespace x5crop {

FilmstripWidget::FilmstripWidget(QWidget* parent)
    : QListWidget(parent)
{
    setObjectName("filmstrip");
    setViewMode(QListView::IconMode);
    setFlow(QListView::LeftToRight);
    setResizeMode(QListView::Adjust);
    setMovement(QListView::Static);
    setWrapping(false);
    setIconSize(QSize(92, 48));
    setGridSize(QSize(110, 72));
    setSpacing(6);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    setSelectionMode(QAbstractItemView::SingleSelection);
    connect(this, &QListWidget::currentRowChanged, this, &FilmstripWidget::scanActivated);
}

void FilmstripWidget::setScans(const QList<ScanItem>& scans)
{
    clear();
    for (const auto& scan : scans) {
        auto* item = new QListWidgetItem(statusIcon(scan.plan.status), scan.displayName);
        item->setToolTip(QString("%1\n%2 warnings")
                             .arg(statusLabel(scan.plan.status))
                             .arg(scan.plan.warnings.size()));
        item->setTextAlignment(Qt::AlignCenter);
        addItem(item);
    }
}

void FilmstripWidget::setCurrentScan(const int row)
{
    if (row >= 0 && row < count()) {
        setCurrentRow(row);
    }
}

QIcon FilmstripWidget::statusIcon(const ScanStatus status) const
{
    QPixmap pixmap(92, 48);
    pixmap.fill(Qt::transparent);

    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(QRectF(0, 0, 92, 48), 8, 8);

    painter.setPen(Qt::NoPen);
    painter.setBrush(statusColor(status));
    painter.drawEllipse(QRectF(74, 7, 14, 14));
    if (status == ScanStatus::NeedsReview) {
        painter.setPen(QColor("#ffffff"));
        painter.setFont(QFont(".AppleSystemUIFont", 8, QFont::DemiBold));
        painter.drawText(QRectF(74, 6, 14, 16), Qt::AlignCenter, "!");
    }

    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    for (int i = 1; i < 6; ++i) {
        const int x = 10 + i * 14;
        painter.drawLine(x, 10, x, 40);
    }

    return QIcon(pixmap);
}

} // namespace x5crop
