#pragma once

#include <QListWidget>

#include "x5crop_native/ScanModels.h"

namespace x5crop {

class FilmstripWidget final : public QListWidget {
    Q_OBJECT

public:
    explicit FilmstripWidget(QWidget* parent = nullptr);

    void setScans(const QList<ScanItem>& scans);
    void setCurrentScan(int row);

signals:
    void scanActivated(int row);

private:
    QIcon statusIcon(ScanStatus status) const;
};

} // namespace x5crop

