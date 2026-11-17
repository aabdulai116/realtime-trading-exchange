// Small self contained test runner, so the engine builds with no downloads.
#include <cstdlib>
#include <iostream>
#include <stdexcept>

#include "exchange/order_book.hpp"

using namespace exch;

static int failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::cerr << __FILE__ << ":" << __LINE__ << "  CHECK failed: "   \
                      << #cond << "\n";                                      \
            failures += 1;                                                   \
        }                                                                    \
    } while (0)

static void resting_orders_set_best_prices() {
    OrderBook book;
    book.add_limit(1, Side::Buy, 99, 5);
    book.add_limit(2, Side::Sell, 101, 5);
    CHECK(book.best_bid().value() == 99);
    CHECK(book.best_ask().value() == 101);
    CHECK(book.order_count() == 2);
}

static void market_order_walks_levels() {
    OrderBook book;
    book.add_limit(1, Side::Sell, 101, 3);
    book.add_limit(2, Side::Sell, 102, 4);
    AddResult r = book.add_market(9, Side::Buy, 5);
    CHECK(r.fills.size() == 2);
    CHECK(r.fills[0].price == 101);
    CHECK(r.fills[0].qty == 3);
    CHECK(r.fills[1].price == 102);
    CHECK(r.fills[1].qty == 2);
    CHECK(r.filled == 5);
    CHECK(book.best_ask().value() == 102);
    CHECK(book.depth(Side::Sell, 5)[0].qty == 2);
}

static void time_priority_within_a_level() {
    OrderBook book;
    AddResult first = book.add_limit(1, Side::Buy, 100, 2);
    book.add_limit(2, Side::Buy, 100, 2);
    AddResult r = book.add_market(9, Side::Sell, 3);
    CHECK(r.fills[0].maker == 1);
    CHECK(r.fills[0].qty == 2);
    CHECK(r.fills[1].maker == 2);
    CHECK(r.fills[1].qty == 1);
    CHECK(!book.get_order(first.id).has_value());
}

static void crossing_limit_trades_at_resting_price_then_rests() {
    OrderBook book;
    book.add_limit(1, Side::Sell, 100, 2);
    AddResult r = book.add_limit(2, Side::Buy, 103, 5);
    CHECK(r.filled == 2);
    CHECK(r.fills[0].price == 100);
    CHECK(r.resting == 3);
    CHECK(book.best_bid().value() == 103);
    CHECK(book.get_order(r.id)->qty == 3);
}

static void limit_does_not_trade_through_its_price() {
    OrderBook book;
    book.add_limit(1, Side::Sell, 105, 2);
    AddResult r = book.add_limit(2, Side::Buy, 104, 2);
    CHECK(r.fills.empty());
    CHECK(book.best_bid().value() == 104);
}

static void cancel_removes_order_and_empty_level() {
    OrderBook book;
    AddResult r = book.add_limit(1, Side::Buy, 99, 5);
    CHECK(book.cancel(r.id));
    CHECK(!book.best_bid().has_value());
    CHECK(!book.cancel(r.id));
}

static void self_trade_prevention_cancels_resting() {
    OrderBook book;
    AddResult mine = book.add_limit(7, Side::Sell, 100, 5);
    book.add_limit(8, Side::Sell, 101, 5);
    AddResult r = book.add_market(7, Side::Buy, 3);
    CHECK(r.self_trade_cancels.size() == 1);
    CHECK(r.self_trade_cancels[0] == mine.id);
    CHECK(r.fills.size() == 1);
    CHECK(r.fills[0].maker == 8);
    CHECK(r.fills[0].price == 101);
}

static void cancel_all_for_trader() {
    OrderBook book;
    book.add_limit(1, Side::Buy, 99, 1);
    book.add_limit(1, Side::Sell, 102, 1);
    book.add_limit(2, Side::Buy, 98, 1);
    CHECK(book.cancel_all(1) == 2);
    CHECK(book.order_count() == 1);
    CHECK(book.orders_for(2).size() == 1);
}

static void rejects_bad_input() {
    OrderBook book;
    bool threw = false;
    try {
        book.add_limit(1, Side::Buy, 100, 0);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);
}

static void volume_and_trade_counts() {
    OrderBook book;
    book.add_limit(1, Side::Sell, 100, 4);
    book.add_market(2, Side::Buy, 3);
    CHECK(book.trade_count() == 1);
    CHECK(book.volume() == 3);
}

int main() {
    resting_orders_set_best_prices();
    market_order_walks_levels();
    time_priority_within_a_level();
    crossing_limit_trades_at_resting_price_then_rests();
    limit_does_not_trade_through_its_price();
    cancel_removes_order_and_empty_level();
    self_trade_prevention_cancels_resting();
    cancel_all_for_trader();
    rejects_bad_input();
    volume_and_trade_counts();

    if (failures == 0) {
        std::cout << "All engine tests passed\n";
        return EXIT_SUCCESS;
    }
    std::cerr << failures << " check(s) failed\n";
    return EXIT_FAILURE;
}
