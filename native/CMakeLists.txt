cmake_minimum_required(VERSION 3.24)

project(X5CropNative
    VERSION 0.1.0
    DESCRIPTION "Native Qt review workspace for X5 Crop"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(X5CROP_MACOS_UNIVERSAL "Build a macOS Universal 2 app bundle" OFF)

if(APPLE AND X5CROP_MACOS_UNIVERSAL AND NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "macOS architectures" FORCE)
endif()

find_package(Qt6 REQUIRED COMPONENTS Widgets)

qt_standard_project_setup()

qt_add_executable(X5CropNative
    MACOSX_BUNDLE
    WIN32
    include/x5crop_native/MainWindow.h
    include/x5crop_native/ReviewCanvas.h
    include/x5crop_native/InspectorPanel.h
    include/x5crop_native/FilmstripWidget.h
    include/x5crop_native/ScanModels.h
    src/main.cpp
    src/MainWindow.cpp
    src/ReviewCanvas.cpp
    src/InspectorPanel.cpp
    src/FilmstripWidget.cpp
    src/ScanModels.cpp
)

target_include_directories(X5CropNative
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(X5CropNative
    PRIVATE
        Qt6::Widgets
)

set_target_properties(X5CropNative PROPERTIES
    OUTPUT_NAME "X5 Crop"
    MACOSX_BUNDLE_GUI_IDENTIFIER "com.rrriiicccooo.x5crop"
    MACOSX_BUNDLE_BUNDLE_NAME "X5 Crop"
    MACOSX_BUNDLE_DISPLAY_NAME "X5 Crop"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    MACOSX_BUNDLE_BUNDLE_VERSION "${PROJECT_VERSION}"
    WIN32_EXECUTABLE TRUE
)

install(TARGETS X5CropNative
    BUNDLE DESTINATION .
    RUNTIME DESTINATION .
)
