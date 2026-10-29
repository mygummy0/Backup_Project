#include <algorithm>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdlib>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <regex>
#include <string>
#include <vector>

namespace fs = std::filesystem;

static std::ofstream g_logfile;
static volatile std::sig_atomic_t g_stop = 0;
static std::mutex g_mu;
static std::condition_variable g_cv;

static std::string now_fmt(const char* fmt) {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
#ifdef _WIN32
    localtime_s(&tm, &t);
#else
    localtime_r(&t, &tm);
#endif
    char buf[32];
    std::strftime(buf, sizeof buf, fmt, &tm);
    return buf;
}

static void logmsg(const std::string& msg) {
    std::string line = "[" + now_fmt("%H:%M:%S") + "] " + msg;
    std::cout << line << std::endl;
    if (g_logfile.is_open()) g_logfile << line << std::endl;
}

static std::string readable_size(double b) {
    const char* units[] = {"B", "KB", "MB", "GB", "TB"};
    for (const char* u : units) {
        if (b < 1024) {
            char buf[64];
            std::snprintf(buf, sizeof buf, "%.1f %s", b, u);
            return buf;
        }
        b /= 1024;
    }
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.1f PB", b);
    return buf;
}

// "30s", "5m", "1h" -> seconds; nullopt if malformed.
static std::optional<long> parse_interval(const std::string& s) {
    if (s.size() < 2) return std::nullopt;
    for (size_t i = 0; i + 1 < s.size(); ++i)
        if (!std::isdigit(static_cast<unsigned char>(s[i]))) return std::nullopt;
    long n = 0;
    try { n = std::stol(s.substr(0, s.size() - 1)); } catch (...) { return std::nullopt; }
    if (n <= 0) return std::nullopt;
    switch (s.back()) {
        case 's': return n;
        case 'm': return n * 60;
        case 'h': return n * 3600;
    }
    return std::nullopt;
}

[[noreturn]] static void usage() {
    std::cerr << "사용법: backup --source <폴더> --target <폴더> [--interval 5m] [--keep N] [--once] [--log-file <파일>]\n";
    std::exit(2);
}

// Rejects missing dirs and a target inside (or equal to) the source, which would recurse forever.
static std::optional<std::string> validate(const fs::path& src, const fs::path& dst, fs::path& csrc, fs::path& cdst) {
    std::error_code ec;
    csrc = fs::canonical(src, ec);
    if (ec || !fs::is_directory(csrc)) return "원본 폴더가 존재하지 않습니다: " + src.string();
    cdst = fs::canonical(dst, ec);
    if (ec || !fs::is_directory(cdst)) return "저장 폴더가 존재하지 않습니다: " + dst.string();
    auto rel = cdst.lexically_relative(csrc);
    if (!rel.empty() && *rel.begin() != "..")
        return std::string("저장 폴더가 원본 폴더 안에 있을 수 없습니다");
    return std::nullopt;
}

static void copy_dir(const fs::path& src, const fs::path& dst, int& skipped) {
    fs::create_directories(dst);
    for (const auto& e : fs::directory_iterator(src)) {
        const auto to = dst / e.path().filename();
        if (e.is_symlink()) {
            ++skipped;
        } else if (e.is_directory()) {
            copy_dir(e.path(), to, skipped);
        } else if (e.is_regular_file()) {
            // never overwrite an existing backup (matches the Go/Rust versions)
            if (fs::exists(to)) throw fs::filesystem_error("already exists", to, std::make_error_code(std::errc::file_exists));
            fs::copy_file(e.path(), to, fs::copy_options::none);
        } else {
            ++skipped;
        }
    }
}

static unsigned long long dir_size(const fs::path& root) {
    unsigned long long total = 0;
    std::error_code ec;
    for (fs::recursive_directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
        std::error_code e2;
        if (it->is_regular_file(e2) && !it->is_symlink(e2)) {
            auto sz = it->file_size(e2);
            if (!e2) total += sz;
        }
    }
    return total;
}

static void prune(const fs::path& dst, const std::string& base, int keep) {
    if (keep <= 0) return;
    // base is a literal directory name, so escape regex metacharacters
    static const std::regex special(R"([.^$|()\[\]{}*+?\\])");
    std::regex re("^" + std::regex_replace(base, special, R"(\$&)") + R"(_\d{8}_\d{6}$)");
    std::vector<std::string> names;
    std::error_code ec;
    for (const auto& e : fs::directory_iterator(dst, ec))
        if (e.is_directory() && std::regex_match(e.path().filename().string(), re))
            names.push_back(e.path().filename().string());
    std::sort(names.begin(), names.end());
    size_t i = 0;
    while (names.size() - i > static_cast<size_t>(keep)) {
        std::error_code rc;
        fs::remove_all(dst / names[i], rc);
        if (rc) logmsg("❌ 오래된 백업 삭제 실패: " + names[i] + " (" + rc.message() + ")");
        else logmsg("🗑 오래된 백업 삭제: " + names[i]);
        ++i;
    }
}

static void run_backup(const fs::path& src, const fs::path& dst, int keep) {
    std::string base = src.filename().string();
    if (base.empty()) base = "backup";
    std::string name = base + "_" + now_fmt("%Y%m%d_%H%M%S");
    int skipped = 0;
    try {
        copy_dir(src, dst / name, skipped);
    } catch (const std::exception& e) {
        logmsg(std::string("❌ 오류 발생: ") + e.what());
        return;
    }
    logmsg("✅ 백업 완료: " + name + " (폴더 용량: " + readable_size(static_cast<double>(dir_size(dst))) + ")");
    if (skipped > 0) logmsg("⚠ 심볼릭 링크/특수 파일 " + std::to_string(skipped) + "개는 건너뛰었습니다");
    prune(dst, base, keep);
}

static void on_signal(int) { g_stop = 1; }

int main(int argc, char** argv) {
    std::string source, target, interval_str = "5m", log_path;
    int keep = 0;
    bool once = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        while (!a.empty() && a[0] == '-') a.erase(0, 1);  // accept -x and --x
        auto val = [&](const char* name) -> std::string {
            if (i + 1 >= argc) { std::cerr << "--" << name << " 에 값이 필요합니다.\n"; usage(); }
            return argv[++i];
        };
        if (a == "source") source = val("source");
        else if (a == "target") target = val("target");
        else if (a == "interval") interval_str = val("interval");
        else if (a == "keep") {
            try { keep = std::stoi(val("keep")); } catch (...) { keep = -1; }
            if (keep < 0) { std::cerr << "--keep 은 0 이상의 정수여야 합니다.\n"; return 2; }
        } else if (a == "once") once = true;
        else if (a == "log-file") log_path = val("log-file");
        else usage();
    }
    if (source.empty() || target.empty()) {
        std::cerr << "--source 와 --target 은 필수입니다.\n";
        usage();
    }
    auto interval = parse_interval(interval_str);
    if (!interval) {
        std::cerr << "잘못된 주기: \"" << interval_str << "\" (예: 30s, 5m, 1h)\n";
        return 2;
    }
    fs::path src, dst;
    if (auto err = validate(source, target, src, dst)) {
        std::cerr << "❌ " << *err << "\n";
        return 1;
    }
    if (!log_path.empty()) {
        g_logfile.open(log_path, std::ios::app);
        if (!g_logfile) { std::cerr << "❌ 로그 파일을 열 수 없습니다: " << log_path << "\n"; return 1; }
    }

    if (once) {
        run_backup(src, dst, keep);
        return 0;
    }

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
    logmsg("자동 백업 시작됨 (주기: " + interval_str + ")");
    while (true) {
        run_backup(src, dst, keep);
        std::unique_lock<std::mutex> lk(g_mu);
        // a signal handler can only set a flag (no mutex/notify), so poll it every 100ms
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(*interval);
        while (!g_stop && std::chrono::steady_clock::now() < deadline)
            g_cv.wait_for(lk, std::chrono::milliseconds(100));
        if (g_stop) {
            logmsg("자동 백업이 사용자에 의해 중지되었습니다.");
            return 0;
        }
    }
}
