cmake_minimum_required(VERSION 3.20)
project(trading_terminal CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------- vcpkg / find_package ----------
find_package(OpenGL REQUIRED)
find_package(glfw3 CONFIG REQUIRED)
find_package(unofficial-sqlite3 CONFIG REQUIRED)

# ---------- Dear ImGui (source in third_party/imgui) ----------
set(IMGUI_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/imgui)
set(IMPLOT_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/implot)

file(GLOB IMGUI_SOURCES
    ${IMGUI_DIR}/*.cpp
    ${IMGUI_DIR}/backends/imgui_impl_glfw.cpp
    ${IMGUI_DIR}/backends/imgui_impl_opengl3.cpp
)
file(GLOB IMPLOT_SOURCES ${IMPLOT_DIR}/*.cpp)

# ---------- Our sources ----------
add_executable(trading_terminal
    src/main.cpp
    src/db.cpp
    src/ui.cpp
    ${IMGUI_SOURCES}
    ${IMPLOT_SOURCES}
)

target_include_directories(trading_terminal PRIVATE
    src
    ${IMGUI_DIR}
    ${IMGUI_DIR}/backends
    ${IMPLOT_DIR}
)

target_link_libraries(trading_terminal PRIVATE
    OpenGL::GL
    glfw
    unofficial::sqlite3::sqlite3
)

# Windows: link against opengl32 explicitly
if(WIN32)
    target_link_libraries(trading_terminal PRIVATE opengl32)
endif()

# Silence MSVC warnings from third-party headers
if(MSVC)
    target_compile_options(trading_terminal PRIVATE /W3 /wd4996)
endif()
