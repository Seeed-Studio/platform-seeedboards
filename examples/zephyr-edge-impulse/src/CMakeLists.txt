target_include_directories(app PRIVATE .)
target_include_directories(app PRIVATE ..)
target_sources(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/ei_at_handlers.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/ei_base64_encode.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/ei_device_nordic.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/ei_sampler.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/flash_memory.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp
)
