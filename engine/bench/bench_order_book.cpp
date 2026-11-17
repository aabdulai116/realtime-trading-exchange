// Throughput and latency benchmark for the matching engine.
//
// Replays a random but realistic message mix: mostly passive limit orders
// near the touch, plenty of cancels, and some aggressive orders.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <vector>

#include "exchange/order_book.hpp"

using namespace exch;
using Clock = std::chrono::steady_clock;

int main(int argc, char** argv) {
    std::size_t messages = 2'000'000;
    if (argc > 1) {
        messages = std::stoull(argv[1]);
    }

    std::mt19937_64 rng(42);
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    std::uniform_int_distribution<int> offset(0, 20);
    std::uniform_int_distribution<int> size(1, 10);
    std::uniform_int_distribution<int> trader(1, 50);

    OrderBook book;
    std::vector<OrderId> live;
    live.reserve(messages);
    std::vector<double> latency_ns;
    latency_ns.reserve(messages);

    Price mid = 10'000;
    std::size_t adds = 0;
    std::size_t cancels = 0;
    std::size_t markets = 0;

    auto start = Clock::now();
    for (std::size_t i = 0; i < messages; ++i) {
        double u = unit(rng);
        auto t0 = Clock::now();

        if (u < 0.60 || live.empty()) {
            Side side = unit(rng) < 0.5 ? Side::Buy : Side::Sell;
            Price price = side == Side::Buy ? mid - offset(rng) : mid + offset(rng);
            AddResult r = book.add_limit(trader(rng), side, price, size(rng));
            if (r.id != 0) {
                live.push_back(r.id);
            }
            adds += 1;
        } else if (u < 0.92) {
            std::uniform_int_distribution<std::size_t> pick(0, live.size() - 1);
            std::size_t k = pick(rng);
            book.cancel(live[k]);
            live[k] = live.back();
            live.pop_back();
            cancels += 1;
        } else {
            Side side = unit(rng) < 0.5 ? Side::Buy : Side::Sell;
            book.add_market(trader(rng), side, size(rng));
            markets += 1;
        }

        auto t1 = Clock::now();
        latency_ns.push_back(
            std::chrono::duration<double, std::nano>(t1 - t0).count());

        if (i % 1000 == 0) {
            mid += unit(rng) < 0.5 ? -1 : 1;  // slow drift keeps the book realistic
        }
    }
    double seconds = std::chrono::duration<double>(Clock::now() - start).count();

    std::sort(latency_ns.begin(), latency_ns.end());
    auto pct = [&](double p) {
        std::size_t idx = static_cast<std::size_t>(p * (latency_ns.size() - 1));
        return latency_ns[idx];
    };

    std::printf("messages        %zu (adds %zu, cancels %zu, market %zu)\n",
                messages, adds, cancels, markets);
    std::printf("trades          %llu\n",
                static_cast<unsigned long long>(book.trade_count()));
    std::printf("throughput      %.2f million msgs/sec\n", messages / seconds / 1e6);
    std::printf("latency p50     %.0f ns\n", pct(0.50));
    std::printf("latency p99     %.0f ns\n", pct(0.99));
    std::printf("latency p99.9   %.0f ns\n", pct(0.999));
    return 0;
}
