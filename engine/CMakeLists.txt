cmake_minimum_required(VERSION 3.18)
project(matching_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_library(orderbook STATIC src/order_book.cpp)
target_include_directories(orderbook PUBLIC include)
set_target_properties(orderbook PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(orderbook PRIVATE /W4)
else()
  target_compile_options(orderbook PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Python module (built by `pip install ./engine` through scikit-build-core).
if(SKBUILD)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(matching_engine src/bindings.cpp)
  target_link_libraries(matching_engine PRIVATE orderbook)
  install(TARGETS matching_engine LIBRARY DESTINATION .)
else()
  # Native tests and benchmark for local development and CI.
  enable_testing()
  add_executable(engine_tests tests/test_order_book.cpp)
  target_link_libraries(engine_tests PRIVATE orderbook)
  add_test(NAME engine_tests COMMAND engine_tests)

  add_executable(engine_bench bench/bench_order_book.cpp)
  target_link_libraries(engine_bench PRIVATE orderbook)
endif()
