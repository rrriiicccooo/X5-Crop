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
    setIconSize(QSize(112, 68));
    setGridSize(QSize(142, 118));
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
    QPixmap pixmap(112, 68);
    pixmap.fill(Qt::transparent);

    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(QRectF(1, 5, 110, 58), 8, 8);

    painter.setPen(Qt::NoPen);
    painter.setBrush(statusColor(status));
    painter.drawEllipse(QRectF(10, 10, 12, 12));
    if (status == ScanStatus::NeedsReview) {
        painter.setPen(QColor("#ffffff"));
        painter.setFont(QFont(".AppleSystemUIFont", 8, QFont::DemiBold));
        painter.drawText(QRectF(10, 8, 12, 14), Qt::AlignCenter, "!");
    }

    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    for (int i = 1; i < 6; ++i) {
        const int x = 8 + i * 17;
        painter.drawLine(x, 28, x, 54);
    }

    painter.setPen(QColor("#667085"));
    painter.setFont(QFont(".AppleSystemUIFont", 8));
    painter.drawText(QRectF(8, 42, 96, 16), Qt::AlignCenter, statusLabel(status));

    return QIcon(pixmap);
}

} // namespace x5crop
