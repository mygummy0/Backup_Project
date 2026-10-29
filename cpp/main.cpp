#include <algorithm>
#include <cctype>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <regex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

static std::ofstream g_logfile;
static volatile std::sig_atomic_t g_stop = 0;

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
    char buf[64];
    for (const char* u : units) {
        if (b < 1024) {
            std::snprintf(buf, sizeof buf, "%.1f %s", b, u);
            return buf;
        }
        b /= 1024;
    }
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
    std::cerr << "사용법: backup --source <폴더> --target <폴더> [--interval 5m] [--keep N] [--once]\n"
                 "               [--mode full|incremental] [--exclude <글롭>]... [--verify] [--dry-run] [--log-file <파일>]\n";
    std::exit(2);
}

[[noreturn]] static void usage_error(const std::string& msg) {
    std::cerr << msg << "\n";
    usage();
}

// ---- exclude globs (see SPEC.md) --------------------------------------------------

// '*' = any run of non-'/', '**' = any run incl. '/', '?' = one non-'/' UTF-8 character.
static bool glob_match(const char* p, const char* pe, const char* s, const char* se) {
    while (p < pe) {
        if (*p == '*') {
            bool deep = (p + 1 < pe && p[1] == '*');
            p += deep ? 2 : 1;
            for (const char* t = s;; ++t) {
                if (glob_match(p, pe, t, se)) return true;
                if (t >= se || (!deep && *t == '/')) return false;
            }
        } else if (*p == '?') {
            if (s >= se || *s == '/') return false;
            ++s;
            while (s < se && (static_cast<unsigned char>(*s) & 0xC0) == 0x80) ++s;  // rest of the character
            ++p;
        } else {
            if (s >= se || *s != *p) return false;
            ++p;
            ++s;
        }
    }
    return s == se;
}

static bool is_excluded(const std::vector<std::string>& patterns, const std::string& rel, const std::string& name) {
    for (const auto& pat : patterns) {
        if (pat.empty()) continue;
        const std::string& target = pat.find('/') != std::string::npos ? rel : name;
        if (glob_match(pat.data(), pat.data() + pat.size(), target.data(), target.data() + target.size())) return true;
    }
    return false;
}

// ---- validation ---------------------------------------------------------------------

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

// ---- copying ------------------------------------------------------------------------

struct Options {
    int keep = 0;
    bool incremental = false;
    std::vector<std::string> excludes;
    bool verify = false;
    bool dry_run = false;
};

struct Stats {
    int copied = 0, reused = 0, excluded = 0, skipped = 0, verified = 0;
};

static bool same_content(const fs::path& a, const fs::path& b) {
    std::ifstream fa(a, std::ios::binary), fb(b, std::ios::binary);
    if (!fa || !fb) throw std::runtime_error("검증용 파일을 열 수 없습니다: " + a.string());
    std::vector<char> ba(64 << 10), bb(64 << 10);
    while (true) {
        fa.read(ba.data(), static_cast<std::streamsize>(ba.size()));
        fb.read(bb.data(), static_cast<std::streamsize>(bb.size()));
        auto na = fa.gcount(), nb = fb.gcount();
        if (na != nb || !std::equal(ba.begin(), ba.begin() + na, bb.begin())) return false;
        if (na < static_cast<std::streamsize>(ba.size())) return true;
    }
}

// Mirrors src into dst. prev (may be empty) is the previous snapshot used for incremental reuse.
// With o.dry_run nothing is written.
static void copy_tree(const Options& o, Stats& st, const fs::path& src, const fs::path& dst,
                      const fs::path& prev, const std::string& rel) {
    for (const auto& e : fs::directory_iterator(src)) {
        const std::string name = e.path().filename().string();
        const std::string rel_path = rel.empty() ? name : rel + "/" + name;
        if (is_excluded(o.excludes, rel_path, name)) { ++st.excluded; continue; }

        const fs::path to = dst / name;
        const auto status = e.symlink_status();
        if (fs::is_directory(status)) {
            if (!o.dry_run) fs::create_directory(to);
            copy_tree(o, st, e.path(), to, prev.empty() ? fs::path() : prev / name, rel_path);
        } else if (fs::is_regular_file(status)) {
            const auto mtime = fs::last_write_time(e.path());
            if (!prev.empty()) {
                std::error_code ec;
                const fs::path pf = prev / name;
                auto ps = fs::symlink_status(pf, ec);
                if (!ec && fs::is_regular_file(ps) && fs::file_size(pf, ec) == e.file_size() &&
                    fs::last_write_time(pf, ec) == mtime) {
                    if (o.dry_run) { ++st.reused; continue; }
                    std::error_code lec;
                    fs::create_hard_link(pf, to, lec);
                    if (!lec) { ++st.reused; continue; }
                }
            }
            ++st.copied;
            if (o.dry_run) continue;
            if (fs::exists(to)) throw std::runtime_error("이미 존재하는 파일입니다: " + to.string());  // never overwrite
            fs::copy_file(e.path(), to, fs::copy_options::none);
            fs::last_write_time(to, mtime);
            if (o.verify) {
                if (!same_content(e.path(), to)) throw std::runtime_error("검증 실패: " + rel_path);
                ++st.verified;
            }
        } else {
            ++st.skipped;
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

// Complete backups of base in dst, oldest first (".partial" dirs never match).
static std::vector<std::string> backup_names(const fs::path& dst, const std::string& base) {
    // base is a literal directory name, so escape regex metacharacters
    static const std::regex special(R"([.^$|()\[\]{}*+?\\])");
    std::regex re("^" + std::regex_replace(base, special, R"(\$&)") + R"(_\d{8}_\d{6}$)");
    std::vector<std::string> names;
    std::error_code ec;
    for (const auto& e : fs::directory_iterator(dst, ec))
        if (e.is_directory() && std::regex_match(e.path().filename().string(), re))
            names.push_back(e.path().filename().string());
    std::sort(names.begin(), names.end());
    return names;
}

static void prune(const fs::path& dst, const std::string& base, int keep) {
    if (keep <= 0) return;
    auto names = backup_names(dst, base);
    size_t i = 0;
    while (names.size() - i > static_cast<size_t>(keep)) {
        std::error_code rc;
        fs::remove_all(dst / names[i], rc);
        if (rc) logmsg("❌ 오래된 백업 삭제 실패: " + names[i] + " (" + rc.message() + ")");
        else logmsg("🗑 오래된 백업 삭제: " + names[i]);
        ++i;
    }
}

static bool run_backup(const fs::path& src, const fs::path& dst, const Options& o) {
    std::string base = src.filename().string();
    if (base.empty()) base = "backup";
    const std::string name = base + "_" + now_fmt("%Y%m%d_%H%M%S");
    const fs::path fin = dst / name;
    const fs::path partial = dst / (name + ".partial");
    std::error_code ec;

    if (fs::symlink_status(fin, ec).type() != fs::file_type::not_found) {
        logmsg("❌ 오류 발생: 이미 존재하는 백업입니다: " + name);
        return false;
    }
    fs::path prev;
    if (o.incremental) {
        auto names = backup_names(dst, base);
        if (!names.empty()) prev = dst / names.back();
    }

    Stats st;
    try {
        if (!o.dry_run && !fs::create_directory(partial))
            throw std::runtime_error("임시 폴더가 이미 존재합니다: " + partial.string());
        copy_tree(o, st, src, partial, prev, "");
        if (!o.dry_run) fs::rename(partial, fin);
    } catch (const std::exception& e) {
        if (!o.dry_run) fs::remove_all(partial, ec);
        logmsg(std::string("❌ 오류 발생: ") + e.what());
        return false;
    }

    if (o.dry_run) logmsg("🧪 [dry-run] 백업 계획: " + name);
    else if (o.verify) logmsg("🔍 검증 완료: " + std::to_string(st.verified) + "개 파일 일치");
    logmsg("📦 복사 " + std::to_string(st.copied) + "개, 재사용 " + std::to_string(st.reused) + "개, 제외 " +
           std::to_string(st.excluded) + "개");
    if (st.skipped > 0) logmsg("⚠ 심볼릭 링크/특수 파일 " + std::to_string(st.skipped) + "개는 건너뛰었습니다");
    if (!o.dry_run) {
        logmsg("✅ 백업 완료: " + name + " (폴더 용량: " + readable_size(static_cast<double>(dir_size(dst))) + ")");
        prune(dst, base, o.keep);
    }
    return true;
}

static void on_signal(int) { g_stop = 1; }

int main(int argc, char** argv) {
    std::string source, target, interval_str = "5m", log_path;
    Options opts;
    bool once = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        while (!a.empty() && a[0] == '-') a.erase(0, 1);  // accept -x and --x
        auto val = [&](const char* name) -> std::string {
            if (i + 1 >= argc) usage_error(std::string("--") + name + " 에 값이 필요합니다.");
            return argv[++i];
        };
        if (a == "source") source = val("source");
        else if (a == "target") target = val("target");
        else if (a == "interval") interval_str = val("interval");
        else if (a == "keep") {
            try { opts.keep = std::stoi(val("keep")); } catch (...) { opts.keep = -1; }
            if (opts.keep < 0) usage_error("--keep 은 0 이상의 정수여야 합니다.");
        } else if (a == "mode") {
            std::string m = val("mode");
            if (m == "full") opts.incremental = false;
            else if (m == "incremental") opts.incremental = true;
            else usage_error("잘못된 모드: \"" + m + "\" (full 또는 incremental)");
        } else if (a == "exclude") {
            std::string p = val("exclude");
            while (!p.empty() && p.front() == '/') p.erase(0, 1);
            while (!p.empty() && p.back() == '/') p.pop_back();
            opts.excludes.push_back(p);
        } else if (a == "once") once = true;
        else if (a == "verify") opts.verify = true;
        else if (a == "dry-run") opts.dry_run = true;
        else if (a == "log-file") log_path = val("log-file");
        else usage();
    }
    if (source.empty() || target.empty()) usage_error("--source 와 --target 은 필수입니다.");
    auto interval = parse_interval(interval_str);
    if (!interval) usage_error("잘못된 주기: \"" + interval_str + "\" (예: 30s, 5m, 1h)");

    fs::path src, dst;
    if (auto err = validate(source, target, src, dst)) {
        std::cerr << "❌ " << *err << "\n";
        return 1;
    }
    if (!log_path.empty()) {
        g_logfile.open(log_path, std::ios::app);
        if (!g_logfile) { std::cerr << "❌ 로그 파일을 열 수 없습니다: " << log_path << "\n"; return 1; }
    }

    if (once || opts.dry_run) return run_backup(src, dst, opts) ? 0 : 1;

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
    logmsg("자동 백업 시작됨 (주기: " + interval_str + ")");
    while (true) {
        run_backup(src, dst, opts);
        // a signal handler can only set a flag, so poll it every 100ms while waiting
        auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(*interval);
        while (!g_stop && std::chrono::steady_clock::now() < deadline)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        if (g_stop) {
            logmsg("자동 백업이 사용자에 의해 중지되었습니다.");
            return 0;
        }
    }
}
