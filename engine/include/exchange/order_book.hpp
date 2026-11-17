// Limit order book with price-time priority matching.
//
// Design notes
//   * Each side is a std::map from price to a FIFO queue (std::list) of
//     orders. The map keeps prices sorted, the list keeps time priority.
//   * An unordered_map from order id to a list iterator gives O(1) cancels,
//     because std::list iterators stay valid when other elements change.
//   * Prices are integer ticks, so there is no floating point rounding.
//   * Self trade prevention: an incoming order never trades against an order
//     from the same trader. The resting order is cancelled instead
//     ("cancel resting"), which is how most real exchanges handle it.
#pragma once

#include <cstdint>
#include <functional>
#include <list>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace exch {

using Price = std::int64_t;
using Qty = std::int64_t;
using OrderId = std::uint64_t;
using TraderId = std::uint32_t;

enum class Side : std::int8_t { Buy = 1, Sell = -1 };

struct Order {
    OrderId id;
    TraderId trader;
    Side side;
    Price price;
    Qty qty;          // remaining quantity
    std::uint64_t seq;  // arrival sequence number
};

struct Fill {
    OrderId taker_order;
    OrderId maker_order;
    TraderId taker;
    TraderId maker;
    Side taker_side;
    Price price;
    Qty qty;
};

struct Level {
    Price price;
    Qty qty;
    std::uint32_t orders;
};

struct AddResult {
    OrderId id = 0;            // 0 when nothing rested in the book
    Qty filled = 0;
    Qty resting = 0;
    std::vector<Fill> fills;
    std::vector<OrderId> self_trade_cancels;
};

class OrderBook {
public:
    // Order ids are first_id, first_id + id_stride, first_id + 2 * id_stride...
    // An exchange running several books gives each book a different first_id
    // and uses the number of books as the stride, so ids never collide.
    explicit OrderBook(OrderId first_id = 1, OrderId id_stride = 1);

    AddResult add_limit(TraderId trader, Side side, Price price, Qty qty);
    AddResult add_market(TraderId trader, Side side, Qty qty);
    bool cancel(OrderId id);
    std::size_t cancel_all(TraderId trader);

    std::optional<Price> best_bid() const;
    std::optional<Price> best_ask() const;
    std::vector<Level> depth(Side side, std::size_t levels) const;
    std::optional<Order> get_order(OrderId id) const;
    std::vector<Order> orders_for(TraderId trader) const;

    std::size_t order_count() const { return index_.size(); }
    std::uint64_t trade_count() const { return trade_count_; }
    Qty volume() const { return volume_; }

private:
    using Queue = std::list<Order>;
    using BidMap = std::map<Price, Queue, std::greater<Price>>;
    using AskMap = std::map<Price, Queue, std::less<Price>>;

    struct Locator {
        Side side;
        Price price;
        Queue::iterator it;
    };

    template <typename Book>
    void match(Book& book, TraderId trader, OrderId taker_id, Side side,
               std::optional<Price> limit, Qty& remaining, AddResult& result);

    OrderId take_id();
    void rest(TraderId trader, Side side, Price price, Qty qty, OrderId id);

    BidMap bids_;
    AskMap asks_;
    std::unordered_map<OrderId, Locator> index_;
    OrderId next_id_;
    OrderId id_stride_;
    std::uint64_t seq_ = 0;
    std::uint64_t trade_count_ = 0;
    Qty volume_ = 0;
};

}  // namespace exch
