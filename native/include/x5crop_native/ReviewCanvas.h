#pragma once

#include <QFrame>
#include <QPixmap>
#include <QString>

#include "x5crop_native/ScanModels.h"

namespace x5crop {

class ReviewCanvas final : public QFrame {
    Q_OBJECT

public:
    explicit ReviewCanvas(QWidget* parent = nullptr);

    void setScan(const ScanItem* item);
    void setShowGrid(bool value);
    void setShowSplitLines(bool value);
    void setShowCropBoxes(bool value);
    void zoomToFit();
    void setZoomPercent(int percent);

protected:
    void paintEvent(QPaintEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

private:
    const ScanItem* m_scan = nullptr;
    bool m_showGrid = true;
    bool m_showSplitLines = true;
    bool m_showCropBoxes = true;
    int m_zoomPercent = 100;

    QRectF filmRect() const;
    void drawEmptyState(QPainter& painter);
    void drawFilmMock(QPainter& painter, const QRectF& rect);
    void drawOverlays(QPainter& painter, const QRectF& rect);
};

} // namespace x5crop

