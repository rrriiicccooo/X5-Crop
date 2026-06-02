#include "x5crop_native/ReviewCanvas.h"

#include <QPainter>
#include <QPainterPath>
#include <QWheelEvent>

namespace x5crop {

ReviewCanvas::ReviewCanvas(QWidget* parent)
    : QFrame(parent)
{
    setMinimumSize(620, 420);
    setFrameShape(QFrame::NoFrame);
    setAutoFillBackground(false);
    setFocusPolicy(Qt::StrongFocus);
}

void ReviewCanvas::setScan(const ScanItem* item)
{
    m_scan = item;
    update();
}

void ReviewCanvas::setShowGrid(const bool value)
{
    m_showGrid = value;
    update();
}

void ReviewCanvas::setShowSplitLines(const bool value)
{
    m_showSplitLines = value;
    update();
}

void ReviewCanvas::setShowCropBoxes(const bool value)
{
    m_showCropBoxes = value;
    update();
}

void ReviewCanvas::zoomToFit()
{
    m_zoomPercent = 100;
    update();
}

void ReviewCanvas::setZoomPercent(const int percent)
{
    m_zoomPercent = std::clamp(percent, 25, 400);
    update();
}

void ReviewCanvas::paintEvent(QPaintEvent*)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.fillRect(rect(), QColor("#101010"));

    if (m_scan == nullptr) {
        drawEmptyState(painter);
        return;
    }

    const QRectF film = filmRect();
    drawFilmMock(painter, film);
    drawOverlays(painter, film);

    painter.setPen(QColor("#f2f2f2"));
    painter.setFont(QFont("Arial", 13, QFont::DemiBold));
    painter.drawText(QRectF(28, 18, width() - 56, 28), Qt::AlignLeft | Qt::AlignVCenter, m_scan->displayName);

    painter.setPen(QColor("#a8a8a8"));
    painter.setFont(QFont("Arial", 10));
    painter.drawText(QRectF(28, 44, width() - 56, 22), Qt::AlignLeft | Qt::AlignVCenter,
                     QString("%1 | %2% zoom").arg(statusLabel(m_scan->plan.status)).arg(m_zoomPercent));
}

void ReviewCanvas::wheelEvent(QWheelEvent* event)
{
    const int step = event->angleDelta().y() > 0 ? 10 : -10;
    setZoomPercent(m_zoomPercent + step);
}

QRectF ReviewCanvas::filmRect() const
{
    const qreal marginX = 42.0;
    const qreal availableW = width() - marginX * 2.0;
    const qreal baseW = availableW * (m_zoomPercent / 100.0);
    const qreal filmW = std::max<qreal>(420.0, baseW);
    const qreal filmH = std::min<qreal>(height() * 0.48, filmW / 5.8);
    const qreal x = (width() - filmW) / 2.0;
    const qreal y = (height() - filmH) / 2.0 + 18.0;
    return QRectF(x, y, filmW, filmH);
}

void ReviewCanvas::drawEmptyState(QPainter& painter)
{
    const QRectF box(width() / 2.0 - 230.0, height() / 2.0 - 90.0, 460.0, 180.0);
    painter.setPen(QPen(QColor("#343434"), 1.0));
    painter.setBrush(QColor("#171717"));
    painter.drawRoundedRect(box, 8.0, 8.0);

    painter.setPen(QColor("#f2f2f2"));
    painter.setFont(QFont("Arial", 16, QFont::DemiBold));
    painter.drawText(box.adjusted(24, 28, -24, -92), Qt::AlignCenter, "Drop TIFF scans here");

    painter.setPen(QColor("#a8a8a8"));
    painter.setFont(QFont("Arial", 11));
    painter.drawText(box.adjusted(38, 86, -38, -28), Qt::AlignCenter | Qt::TextWordWrap,
                     "Add files or folders to start a review batch. Automatic detection will create crop plans for approval.");
}

void ReviewCanvas::drawFilmMock(QPainter& painter, const QRectF& rect)
{
    painter.setPen(QPen(QColor("#343434"), 1.0));
    painter.setBrush(QColor("#1a1a1a"));
    painter.drawRoundedRect(rect, 6.0, 6.0);

    const QRectF inner = rect.adjusted(18, 18, -18, -18);
    QLinearGradient gradient(inner.topLeft(), inner.bottomRight());
    gradient.setColorAt(0.0, QColor("#222222"));
    gradient.setColorAt(0.45, QColor("#2c2c2c"));
    gradient.setColorAt(1.0, QColor("#111111"));
    painter.setPen(Qt::NoPen);
    painter.setBrush(gradient);
    painter.drawRoundedRect(inner, 4.0, 4.0);

    painter.setPen(QPen(QColor(255, 255, 255, 20), 1.0));
    for (int i = 0; i < 12; ++i) {
        const qreal y = inner.top() + (i + 1) * inner.height() / 13.0;
        painter.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y));
    }
}

void ReviewCanvas::drawOverlays(QPainter& painter, const QRectF& rect)
{
    const QRectF outer = rect.adjusted(32, 30, -32, -30);

    painter.setBrush(Qt::NoBrush);
    painter.setPen(QPen(QColor("#56d364"), 2.0));
    painter.drawRect(outer);

    const int frames = m_scan != nullptr ? std::max(1, m_scan->plan.frameCount) : 6;
    const qreal frameW = outer.width() / frames;

    if (m_showGrid) {
        painter.setPen(QPen(QColor("#bc8cff"), 1.0, Qt::DashLine));
        for (int i = 1; i < frames; ++i) {
            const qreal x = outer.left() + i * frameW;
            painter.drawLine(QPointF(x, outer.top()), QPointF(x, outer.bottom()));
        }
    }

    if (m_showCropBoxes) {
        painter.setPen(QPen(QColor("#58a6ff"), 1.7));
        for (int i = 0; i < frames; ++i) {
            const QRectF crop(outer.left() + i * frameW + 4, outer.top() + 6, frameW - 8, outer.height() - 12);
            painter.drawRect(crop);
            painter.setPen(QColor("#58a6ff"));
            painter.setFont(QFont("Arial", 10, QFont::DemiBold));
            painter.drawText(crop.adjusted(8, 8, -8, -8), Qt::AlignTop | Qt::AlignLeft, QString::number(i + 1));
            painter.setPen(QPen(QColor("#58a6ff"), 1.7));
        }
    }

    if (m_showSplitLines) {
        painter.setPen(QPen(QColor("#ff6b6b"), 2.0));
        painter.setBrush(QColor("#ff6b6b"));
        for (int i = 1; i < frames; ++i) {
            const qreal x = outer.left() + i * frameW;
            painter.drawLine(QPointF(x, outer.top() - 12), QPointF(x, outer.bottom() + 12));
            painter.drawRoundedRect(QRectF(x - 5, outer.top() - 20, 10, 12), 3, 3);
        }
    }
}

} // namespace x5crop

