#include <QApplication>
#include <QSurfaceFormat>

#include "x5crop_native/MainWindow.h"

int main(int argc, char* argv[])
{
    QApplication app(argc, argv);
    QApplication::setApplicationName("X5 Crop");
    QApplication::setApplicationDisplayName("X5 Crop");
    QApplication::setOrganizationName("rrriiicccooo");
    QApplication::setOrganizationDomain("github.com/rrriiicccooo");

    x5crop::MainWindow window;
    window.show();

    return QApplication::exec();
}

