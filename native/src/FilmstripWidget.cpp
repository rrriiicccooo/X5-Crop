#include "x5crop_native/FilmstripWidget.h"

#include <QPainter>
#include <QPixmap>

namespace x5crop {

FilmstripWidget::FilmstripWidget(QWidget* parent)
    : QListWidget(parent)
{
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
    pixmap.fill(QColor("#151515"));

    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(QPen(QColor("#343434"), 1.0));
    painter.setBrush(QColor("#222222"));
    painter.drawRoundedRect(QRectF(1, 1, 110, 66), 5, 5);

    painter.setPen(Qt::NoPen);
    painter.setBrush(statusColor(status));
    painter.drawRoundedRect(QRectF(8, 8, 34, 12), 4, 4);

    painter.setPen(QPen(QColor("#444444"), 1.0));
    for (int i = 1; i < 6; ++i) {
        const int x = 8 + i * 17;
        painter.drawLine(x, 28, x, 58);
    }

    painter.setPen(QColor("#a8a8a8"));
    painter.setFont(QFont("Arial", 8));
    painter.drawText(QRectF(8, 42, 96, 16), Qt::AlignCenter, statusLabel(status));

    return QIcon(pixmap);
}

} // namespace x5crop

