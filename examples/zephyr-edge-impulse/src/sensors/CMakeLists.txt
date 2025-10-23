target_include_directories(app PRIVATE .)
target_sources(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/ei_inertial_sensor.cpp
)