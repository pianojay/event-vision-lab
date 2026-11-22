// A CPU-only sampled sensor microbenchmark. No renderer or GPU readback is timed.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

struct Event {
    double timestamp;
    std::uint16_t x, y;
    std::int8_t polarity;
};

constexpr float threshold = 0.25f;

int count_events(float current, float& reference) {
    float delta = current - reference;
    int count = static_cast<int>(std::floor(std::abs(delta) / threshold + 1e-6f));
    int polarity = delta >= 0 ? 1 : -1;
    reference += polarity * count * threshold;
    return polarity * count;
}

void verify() {
    float reference = 0;
    if (count_events(0, reference) != 0 ||
        count_events(0.625f, reference) != 2 || reference != 0.5f ||
        count_events(0.875f, reference) != 1 || reference != 0.75f ||
        count_events(0, reference) != -3 || reference != 0)
        throw std::runtime_error("threshold/residual/polarity check failed");
    // Sampling only the endpoints cannot recover an intervening flash.
    reference = 0;
    if (count_events(0, reference) != 0)
        throw std::runtime_error("static-scene check failed");
}

void benchmark(int width, int height, int active_stride, bool comma) {
    constexpr int warmup = 60, samples = 600;
    constexpr double simulated_hz = 240;
    const int pixels = width * height;
    const float changes[] = {0, 0.625f, 0, -0.625f};
    std::vector<std::vector<float>> inputs(4, std::vector<float>(pixels));
    std::vector<float> reference(pixels), previous(pixels);
    std::vector<Event> events;
    events.reserve(static_cast<std::size_t>(pixels) * 4);
    for (int i = 0; i < pixels; ++i) {
        float base = 0.5f + static_cast<float>(i % 17) * 0.01f;
        reference[i] = previous[i] = std::log(base);
        for (int phase = 0; phase < 4; ++phase)
            inputs[phase][i] = base * std::exp(i % active_stride == 0 ? changes[phase] : 0);
    }
    std::vector<double> durations;
    std::uint64_t total_events = 0;
    double checksum = 0;
    for (int step = 0; step < warmup + samples; ++step) {
        const auto& input = inputs[step % 4];
        auto start = std::chrono::steady_clock::now();
        events.clear();
        for (int i = 0; i < pixels; ++i) {
            float current = std::log(std::max(input[i], 1e-6f));
            float old_reference = reference[i];
            int signed_count = count_events(current, reference[i]);
            int polarity = signed_count >= 0 ? 1 : -1;
            int count = std::abs(signed_count);
            for (int k = 1; k <= count; ++k) {
                float crossing = old_reference + polarity * k * threshold;
                float denominator = current - previous[i];
                double fraction = denominator == 0 ? 1 :
                    std::clamp(static_cast<double>((crossing - previous[i]) / denominator), 0.0, 1.0);
                events.push_back({(step + fraction) / simulated_hz,
                    static_cast<std::uint16_t>(i % width),
                    static_cast<std::uint16_t>(i / width),
                    static_cast<std::int8_t>(polarity)});
            }
            previous[i] = current;
        }
        auto finish = std::chrono::steady_clock::now();
        if (!events.empty()) checksum += events.front().timestamp + events.back().polarity;
        if (step >= warmup) {
            durations.push_back(std::chrono::duration<double, std::milli>(finish - start).count());
            total_events += events.size();
        }
    }
    double total_ms = 0;
    for (double duration : durations) total_ms += duration;
    std::sort(durations.begin(), durations.end());
    const double simulated_seconds = samples / simulated_hz;
    if (comma) std::cout << ",\n";
    std::cout << "    {\"width\":" << width << ",\"height\":" << height
        << ",\"active_fraction\":" << 1.0 / active_stride
        << ",\"median_ms\":" << durations[samples / 2]
        << ",\"p95_ms\":" << durations[static_cast<int>(samples * 0.95) - 1]
        << ",\"mean_ms\":" << total_ms / samples
        << ",\"measured_samples_per_second\":" << samples * 1000.0 / total_ms
        << ",\"events_per_simulated_second\":" << total_events / simulated_seconds
        << ",\"event_bytes\":" << sizeof(Event)
        << ",\"checksum\":" << checksum << "}";
}

int main() {
    try {
        verify();
        std::cout << std::fixed << std::setprecision(6)
            << "{\n  \"kind\":\"single-thread CPU sensor microbenchmark\",\n"
            << "  \"self_check\":\"passed\",\n"
            << "  \"simulated_sample_hz\":240,\n"
            << "  \"warmup_samples\":60,\n  \"measured_samples\":600,\n"
            << "  \"contrast_threshold\":0.25,\n"
            << "  \"scope\":\"log intensity, residual thresholds, interpolated timestamps, event vector; precomputed input; no rendering, transfer, sorting, noise, refractory, display or inference\",\n"
            << "  \"cases\":[\n";
        benchmark(240, 180, 16, false);
        benchmark(320, 240, 16, true);
        benchmark(640, 480, 16, true);
        benchmark(240, 180, 1, true);
        benchmark(320, 240, 1, true);
        benchmark(640, 480, 1, true);
        std::cout << "\n  ]\n}\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
