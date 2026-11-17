#include "exchange/order_book.hpp"

#include <algorithm>
#include <stdexcept>

namespace exch {

namespace {

bool crosses(Side side, Price resting_price, const std::optional<Price>& limit) {
    if (!limit) {
        return true;  // market order
    }
    if (side == Side::Buy) {
        return resting_price <= *limit;
    }
    return resting_price >= *limit;
}

}  // namespace

OrderBook::OrderBook(OrderId first_id, OrderId id_stride)
    : next_id_(first_id), id_stride_(id_stride) {
    if (first_id == 0 || id_stride == 0) {
        throw std::invalid_argument("first_id and id_stride must be positive");
    }
}

OrderId OrderBook::take_id() {
    OrderId id = next_id_;
    next_id_ += id_stride_;
    return id;
}

AddResult OrderBook::add_limit(TraderId trader, Side side, Price price, Qty qty) {
    if (qty <= 0) {
        throw std::invalid_argument("quantity must be positive");
    }
    if (price <= 0) {
        throw std::invalid_argument("price must be positive");
    }
    AddResult result;
    OrderId id = take_id();
    Qty remaining = qty;

    if (side == Side::Buy) {
        match(asks_, trader, id, side, price, remaining, result);
    } else {
        match(bids_, trader, id, side, price, remaining, result);
    }

    result.filled = qty - remaining;
    result.resting = remaining;
    if (remaining > 0) {
        rest(trader, side, price, remaining, id);
        result.id = id;
    }
    return result;
}

AddResult OrderBook::add_market(TraderId trader, Side side, Qty qty) {
    if (qty <= 0) {
        throw std::invalid_argument("quantity must be positive");
    }
    AddResult result;
    OrderId id = take_id();
    Qty remaining = qty;

    if (side == Side::Buy) {
        match(asks_, trader, id, side, std::nullopt, remaining, result);
    } else {
        match(bids_, trader, id, side, std::nullopt, remaining, result);
    }

    // Unfilled market quantity is cancelled, never rested.
    result.filled = qty - remaining;
    result.resting = 0;
    return result;
}

template <typename Book>
void OrderBook::match(Book& book, TraderId trader, OrderId taker_id, Side side,
                      std::optional<Price> limit, Qty& remaining, AddResult& result) {
    while (remaining > 0 && !book.empty()) {
        auto level = book.begin();
        if (!crosses(side, level->first, limit)) {
            break;
        }
        Queue& queue = level->second;

        while (remaining > 0 && !queue.empty()) {
            Order& resting = queue.front();

            if (resting.trader == trader) {
                // Self trade prevention: pull our own resting order.
                result.self_trade_cancels.push_back(resting.id);
                index_.erase(resting.id);
                queue.pop_front();
                continue;
            }

            Qty traded = std::min(remaining, resting.qty);
            Fill fill;
            fill.taker_order = taker_id;
            fill.maker_order = resting.id;
            fill.taker = trader;
            fill.maker = resting.trader;
            fill.taker_side = side;
            fill.price = resting.price;
            fill.qty = traded;
            result.fills.push_back(fill);

            remaining -= traded;
            resting.qty -= traded;
            trade_count_ += 1;
            volume_ += traded;

            if (resting.qty == 0) {
                index_.erase(resting.id);
                queue.pop_front();
            }
        }

        if (queue.empty()) {
            book.erase(level);
        }
    }
}

void OrderBook::rest(TraderId trader, Side side, Price price, Qty qty, OrderId id) {
    Order order{id, trader, side, price, qty, seq_++};
    Queue* queue = nullptr;
    if (side == Side::Buy) {
        queue = &bids_[price];
    } else {
        queue = &asks_[price];
    }
    queue->push_back(order);
    auto it = std::prev(queue->end());
    index_.emplace(id, Locator{side, price, it});
}

bool OrderBook::cancel(OrderId id) {
    auto found = index_.find(id);
    if (found == index_.end()) {
        return false;
    }
    const Locator& loc = found->second;
    if (loc.side == Side::Buy) {
        auto level = bids_.find(loc.price);
        level->second.erase(loc.it);
        if (level->second.empty()) {
            bids_.erase(level);
        }
    } else {
        auto level = asks_.find(loc.price);
        level->second.erase(loc.it);
        if (level->second.empty()) {
            asks_.erase(level);
        }
    }
    index_.erase(found);
    return true;
}

std::size_t OrderBook::cancel_all(TraderId trader) {
    std::vector<OrderId> ids;
    for (const auto& entry : index_) {
        if (entry.second.it->trader == trader) {
            ids.push_back(entry.first);
        }
    }
    for (OrderId id : ids) {
        cancel(id);
    }
    return ids.size();
}

std::optional<Price> OrderBook::best_bid() const {
    if (bids_.empty()) {
        return std::nullopt;
    }
    return bids_.begin()->first;
}

std::optional<Price> OrderBook::best_ask() const {
    if (asks_.empty()) {
        return std::nullopt;
    }
    return asks_.begin()->first;
}

std::vector<Level> OrderBook::depth(Side side, std::size_t levels) const {
    std::vector<Level> out;
    auto collect = [&](const auto& book) {
        for (const auto& [price, queue] : book) {
            if (out.size() >= levels) {
                break;
            }
            Qty total = 0;
            for (const Order& order : queue) {
                total += order.qty;
            }
            out.push_back(Level{price, total, static_cast<std::uint32_t>(queue.size())});
        }
    };
    if (side == Side::Buy) {
        collect(bids_);
    } else {
        collect(asks_);
    }
    return out;
}

std::optional<Order> OrderBook::get_order(OrderId id) const {
    auto found = index_.find(id);
    if (found == index_.end()) {
        return std::nullopt;
    }
    return *found->second.it;
}

std::vector<Order> OrderBook::orders_for(TraderId trader) const {
    std::vector<Order> out;
    for (const auto& entry : index_) {
        if (entry.second.it->trader == trader) {
            out.push_back(*entry.second.it);
        }
    }
    std::sort(out.begin(), out.end(),
              [](const Order& a, const Order& b) { return a.seq < b.seq; });
    return out;
}

}  // namespace exch
