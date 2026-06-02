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
    painter.fillRect(rect(), QColor("#f4f6f9"));

    if (m_scan == nullptr) {
        drawEmptyState(painter);
        return;
    }

    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(QRectF(24, 24, width() - 48, 48), 10, 10);

    painter.setPen(QColor("#1f2937"));
    painter.setFont(QFont(".AppleSystemUIFont", 16, QFont::DemiBold));
    painter.drawText(QRectF(46, 32, 260, 32), Qt::AlignLeft | Qt::AlignVCenter, m_scan->displayName);

    painter.setPen(QColor("#667085"));
    painter.setFont(QFont(".AppleSystemUIFont", 12));
    painter.drawText(QRectF(width() - 350, 32, 320, 32), Qt::AlignRight | Qt::AlignVCenter,
                     "Fit   100%   Pan   Crop   Grid   Analysis");

    const QRectF film = filmRect();
    drawFilmMock(painter, film);
    drawOverlays(painter, film);

    const QRectF note(width() / 2.0 - 315, film.bottom() + 48, 630, 92);
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(note, 12, 12);
    painter.setPen(QColor("#667085"));
    painter.setFont(QFont(".AppleSystemUIFont", 10, QFont::DemiBold));
    painter.drawText(note.adjusted(24, 16, -24, -58), Qt::AlignLeft | Qt::AlignVCenter, "REVIEW NOTE");
    painter.setFont(QFont(".AppleSystemUIFont", 12));
    painter.drawText(note.adjusted(24, 38, -24, -34), Qt::AlignLeft | Qt::AlignVCenter,
                     QString("Confidence: %1%. %2")
                         .arg(m_scan->plan.confidencePercent)
                         .arg(m_scan->plan.warnings.isEmpty() ? "Ready for review." : m_scan->plan.warnings.first()));
    painter.drawText(note.adjusted(24, 60, -24, -12), Qt::AlignLeft | Qt::AlignVCenter,
                     "Drag the red line, or approve if the crop looks right.");
}

void ReviewCanvas::wheelEvent(QWheelEvent* event)
{
    const int step = event->angleDelta().y() > 0 ? 10 : -10;
    setZoomPercent(m_zoomPercent + step);
}

QRectF ReviewCanvas::filmRect() const
{
    const qreal marginX = 72.0;
    const qreal availableW = width() - marginX * 2.0;
    const qreal baseW = std::min<qreal>(760.0, availableW) * (m_zoomPercent / 100.0);
    const qreal filmW = std::max<qreal>(520.0, baseW);
    const qreal filmH = std::min<qreal>(height() * 0.42, filmW / 2.4);
    const qreal x = (width() - filmW) / 2.0;
    const qreal y = std::max<qreal>(104.0, (height() - filmH) / 2.0 - 38.0);
    return QRectF(x, y, filmW, filmH);
}

void ReviewCanvas::drawEmptyState(QPainter& painter)
{
    const QRectF box(width() / 2.0 - 230.0, height() / 2.0 - 90.0, 460.0, 180.0);
    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(box, 8.0, 8.0);

    painter.setPen(QColor("#1f2937"));
    painter.setFont(QFont(".AppleSystemUIFont", 16, QFont::DemiBold));
    painter.drawText(box.adjusted(24, 28, -24, -92), Qt::AlignCenter, "Drop TIFF scans here");

    painter.setPen(QColor("#667085"));
    painter.setFont(QFont(".AppleSystemUIFont", 11));
    painter.drawText(box.adjusted(38, 86, -38, -28), Qt::AlignCenter | Qt::TextWordWrap,
                     "Add files or folders to start a review batch. Automatic detection will create crop plans for approval.");
}

void ReviewCanvas::drawFilmMock(QPainter& painter, const QRectF& rect)
{
    painter.setPen(QPen(QColor("#d8dee8"), 1.0));
    painter.setBrush(QColor("#ffffff"));
    painter.drawRoundedRect(rect, 6.0, 6.0);

    const QRectF inner = rect.adjusted(18, 18, -18, -18);
    QLinearGradient gradient(inner.topLeft(), inner.bottomRight());
    gradient.setColorAt(0.0, QColor("#d6dde7"));
    gradient.setColorAt(0.11, QColor("#94a3b8"));
    gradient.setColorAt(0.23, QColor("#edf1f6"));
    gradient.setColorAt(0.38, QColor("#9aa7b8"));
    gradient.setColorAt(0.52, QColor("#f4f6f9"));
    gradient.setColorAt(0.66, QColor("#8798ad"));
    gradient.setColorAt(0.82, QColor("#e8edf4"));
    gradient.setColorAt(1.0, QColor("#a4afbf"));
    painter.setPen(Qt::NoPen);
    painter.setBrush(gradient);
    painter.drawRoundedRect(inner, 4.0, 4.0);

    painter.setPen(QPen(QColor(127, 147, 182, 36), 1.0));
    for (int i = 0; i < 12; ++i) {
        const qreal y = inner.top() + (i + 1) * inner.height() / 13.0;
        painter.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y));
    }
}

void ReviewCanvas::drawOverlays(QPainter& painter, const QRectF& rect)
{
    const QRectF outer = rect.adjusted(32, 30, -32, -30);

    painter.setBrush(Qt::NoBrush);
    painter.setPen(QPen(QColor("#22a06b"), 2.0));
    painter.drawRect(outer);

    const int frames = m_scan != nullptr ? std::max(1, m_scan->plan.frameCount) : 6;
    const qreal frameW = outer.width() / frames;

    if (m_showGrid) {
        painter.setPen(QPen(QColor("#8b6fd6"), 1.0, Qt::DashLine));
        for (int i = 1; i < frames; ++i) {
            const qreal x = outer.left() + i * frameW;
            painter.drawLine(QPointF(x, outer.top()), QPointF(x, outer.bottom()));
        }
    }

    if (m_showCropBoxes) {
        painter.setPen(QPen(QColor("#3d8bfd"), 1.7));
        for (int i = 0; i < frames; ++i) {
            const QRectF crop(outer.left() + i * frameW + 4, outer.top() + 6, frameW - 8, outer.height() - 12);
            painter.drawRect(crop);
            painter.setPen(QColor("#3d8bfd"));
            painter.setFont(QFont(".AppleSystemUIFont", 10, QFont::DemiBold));
            painter.drawText(crop.adjusted(8, 8, -8, -8), Qt::AlignTop | Qt::AlignLeft, QString::number(i + 1));
            painter.setPen(QPen(QColor("#3d8bfd"), 1.7));
        }
    }

    if (m_showSplitLines) {
        painter.setPen(QPen(QColor("#e85d5d"), 2.0));
        painter.setBrush(QColor("#e85d5d"));
        for (int i = 1; i < frames; ++i) {
            const qreal x = outer.left() + i * frameW;
            painter.drawLine(QPointF(x, outer.top() - 12), QPointF(x, outer.bottom() + 12));
            painter.drawRoundedRect(QRectF(x - 5, outer.top() - 20, 10, 12), 3, 3);
        }
    }
}

} // namespace x5crop
