// Python bindings so the FastAPI server can call the C++ engine directly.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "exchange/order_book.hpp"

namespace py = pybind11;
using namespace exch;

PYBIND11_MODULE(matching_engine, m) {
    m.doc() = "C++ limit order book with price-time priority matching";

    py::enum_<Side>(m, "Side")
        .value("BUY", Side::Buy)
        .value("SELL", Side::Sell);

    py::class_<Order>(m, "Order")
        .def_readonly("id", &Order::id)
        .def_readonly("trader", &Order::trader)
        .def_readonly("side", &Order::side)
        .def_readonly("price", &Order::price)
        .def_readonly("qty", &Order::qty)
        .def_readonly("seq", &Order::seq);

    py::class_<Fill>(m, "Fill")
        .def_readonly("taker_order", &Fill::taker_order)
        .def_readonly("maker_order", &Fill::maker_order)
        .def_readonly("taker", &Fill::taker)
        .def_readonly("maker", &Fill::maker)
        .def_readonly("taker_side", &Fill::taker_side)
        .def_readonly("price", &Fill::price)
        .def_readonly("qty", &Fill::qty);

    py::class_<Level>(m, "Level")
        .def_readonly("price", &Level::price)
        .def_readonly("qty", &Level::qty)
        .def_readonly("orders", &Level::orders);

    py::class_<AddResult>(m, "AddResult")
        .def_readonly("id", &AddResult::id)
        .def_readonly("filled", &AddResult::filled)
        .def_readonly("resting", &AddResult::resting)
        .def_readonly("fills", &AddResult::fills)
        .def_readonly("self_trade_cancels", &AddResult::self_trade_cancels);

    py::class_<OrderBook>(m, "OrderBook")
        .def(py::init<>())
        .def("add_limit", &OrderBook::add_limit,
             py::arg("trader"), py::arg("side"), py::arg("price"), py::arg("qty"))
        .def("add_market", &OrderBook::add_market,
             py::arg("trader"), py::arg("side"), py::arg("qty"))
        .def("cancel", &OrderBook::cancel, py::arg("order_id"))
        .def("cancel_all", &OrderBook::cancel_all, py::arg("trader"))
        .def("best_bid", &OrderBook::best_bid)
        .def("best_ask", &OrderBook::best_ask)
        .def("depth", &OrderBook::depth, py::arg("side"), py::arg("levels") = 10)
        .def("get_order", &OrderBook::get_order, py::arg("order_id"))
        .def("orders_for", &OrderBook::orders_for, py::arg("trader"))
        .def_property_readonly("order_count", &OrderBook::order_count)
        .def_property_readonly("trade_count", &OrderBook::trade_count)
        .def_property_readonly("volume", &OrderBook::volume);
}
