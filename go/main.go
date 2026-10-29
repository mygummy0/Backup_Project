package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var logFile *os.File

func logf(format string, a ...any) {
	line := fmt.Sprintf("[%s] %s", time.Now().Format("15:04:05"), fmt.Sprintf(format, a...))
	fmt.Println(line)
	if logFile != nil {
		fmt.Fprintln(logFile, line)
	}
}

// ---- options ----------------------------------------------------------------

type options struct {
	src, dst    string
	keep        int
	incremental bool
	excludes    []string
	verify      bool
	dryRun      bool
}

type stringList []string

func (s *stringList) String() string     { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error { *s = append(*s, v); return nil }

// parseInterval accepts "30s", "1m", "1h" (positive number + unit).
func parseInterval(s string) (time.Duration, error) {
	bad := fmt.Errorf("잘못된 주기: %q (예: 30s, 5m, 1h)", s)
	if len(s) < 2 {
		return 0, bad
	}
	n, err := strconv.Atoi(s[:len(s)-1])
	if err != nil || n <= 0 {
		return 0, bad
	}
	switch s[len(s)-1] {
	case 's':
		return time.Duration(n) * time.Second, nil
	case 'm':
		return time.Duration(n) * time.Minute, nil
	case 'h':
		return time.Duration(n) * time.Hour, nil
	}
	return 0, bad
}

func readableSize(b float64) string {
	for _, u := range []string{"B", "KB", "MB", "GB", "TB"} {
		if b < 1024 {
			return fmt.Sprintf("%.1f %s", b, u)
		}
		b /= 1024
	}
	return fmt.Sprintf("%.1f PB", b)
}

// ---- exclude globs (see SPEC.md) --------------------------------------------

// globMatch: '*' = any run of non-'/', '**' = any run incl. '/', '?' = one non-'/' rune.
func globMatch(p, s []rune) bool {
	for len(p) > 0 {
		switch p[0] {
		case '*':
			deep := len(p) > 1 && p[1] == '*'
			if deep {
				p = p[2:]
			} else {
				p = p[1:]
			}
			for i := 0; ; i++ {
				if globMatch(p, s[i:]) {
					return true
				}
				if i >= len(s) || (!deep && s[i] == '/') {
					return false
				}
			}
		case '?':
			if len(s) == 0 || s[0] == '/' {
				return false
			}
			p, s = p[1:], s[1:]
		default:
			if len(s) == 0 || s[0] != p[0] {
				return false
			}
			p, s = p[1:], s[1:]
		}
	}
	return len(s) == 0
}

func excluded(patterns []string, rel, name string) bool {
	for _, pat := range patterns {
		pat = strings.Trim(pat, "/")
		if pat == "" {
			continue
		}
		target := name
		if strings.Contains(pat, "/") {
			target = rel
		}
		if globMatch([]rune(pat), []rune(target)) {
			return true
		}
	}
	return false
}

// ---- validation ---------------------------------------------------------------

// validate rejects missing dirs and a target located inside (or equal to) the source,
// which would otherwise recurse forever.
func validate(src, dst string) (string, string, error) {
	absSrc, err := filepath.Abs(src)
	if err != nil {
		return "", "", err
	}
	absDst, err := filepath.Abs(dst)
	if err != nil {
		return "", "", err
	}
	if st, err := os.Stat(absSrc); err != nil || !st.IsDir() {
		return "", "", fmt.Errorf("원본 폴더가 존재하지 않습니다: %s", absSrc)
	}
	if st, err := os.Stat(absDst); err != nil || !st.IsDir() {
		return "", "", fmt.Errorf("저장 폴더가 존재하지 않습니다: %s", absDst)
	}
	if r, err := filepath.EvalSymlinks(absSrc); err == nil {
		absSrc = r
	}
	if r, err := filepath.EvalSymlinks(absDst); err == nil {
		absDst = r
	}
	rel, err := filepath.Rel(absSrc, absDst)
	if err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", "", fmt.Errorf("저장 폴더가 원본 폴더 안에 있을 수 없습니다")
	}
	return absSrc, absDst, nil
}

// ---- copying ------------------------------------------------------------------

type stats struct{ copied, reused, excluded, skipped, verified int }

func sameContent(a, b string) (bool, error) {
	fa, err := os.Open(a)
	if err != nil {
		return false, err
	}
	defer fa.Close()
	fb, err := os.Open(b)
	if err != nil {
		return false, err
	}
	defer fb.Close()
	ba, bb := make([]byte, 64<<10), make([]byte, 64<<10)
	for {
		na, ea := io.ReadFull(fa, ba)
		nb, eb := io.ReadFull(fb, bb)
		if na != nb || !bytes.Equal(ba[:na], bb[:nb]) {
			return false, nil
		}
		if ea != nil || eb != nil {
			if (ea == io.EOF || ea == io.ErrUnexpectedEOF) && (eb == io.EOF || eb == io.ErrUnexpectedEOF) {
				return true, nil
			}
			if ea != nil && ea != io.EOF && ea != io.ErrUnexpectedEOF {
				return false, ea
			}
			return false, eb
		}
	}
}

func copyFile(src, dst string, info fs.FileInfo) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, info.Mode().Perm())
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Chtimes(dst, info.ModTime(), info.ModTime())
}

// copyTree mirrors srcDir into dstDir. prevDir (may be "") is the previous snapshot used
// for incremental reuse. With o.dryRun nothing is written.
func copyTree(o *options, st *stats, srcDir, dstDir, prevDir, rel string) error {
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return err
	}
	for _, e := range entries {
		name := e.Name()
		relPath := name
		if rel != "" {
			relPath = rel + "/" + name
		}
		if excluded(o.excludes, relPath, name) {
			st.excluded++
			continue
		}
		info, err := os.Lstat(filepath.Join(srcDir, name))
		if err != nil {
			return err
		}
		from, to := filepath.Join(srcDir, name), filepath.Join(dstDir, name)
		switch {
		case info.IsDir():
			if !o.dryRun {
				if err := os.Mkdir(to, info.Mode().Perm()|0o700); err != nil {
					return err
				}
			}
			prevSub := ""
			if prevDir != "" {
				prevSub = filepath.Join(prevDir, name)
			}
			if err := copyTree(o, st, from, to, prevSub, relPath); err != nil {
				return err
			}
		case info.Mode().IsRegular():
			if prevDir != "" {
				pi, perr := os.Lstat(filepath.Join(prevDir, name))
				if perr == nil && pi.Mode().IsRegular() && pi.Size() == info.Size() && pi.ModTime().Equal(info.ModTime()) {
					if o.dryRun || os.Link(filepath.Join(prevDir, name), to) == nil {
						st.reused++
						continue
					}
				}
			}
			st.copied++
			if o.dryRun {
				continue
			}
			if err := copyFile(from, to, info); err != nil {
				return err
			}
			if o.verify {
				same, err := sameContent(from, to)
				if err != nil {
					return err
				}
				if !same {
					return fmt.Errorf("검증 실패: %s", relPath)
				}
				st.verified++
			}
		default:
			st.skipped++
		}
	}
	return nil
}

func dirSize(root string) int64 {
	var total int64
	filepath.WalkDir(root, func(_ string, d fs.DirEntry, err error) error {
		if err == nil && d.Type().IsRegular() {
			if info, e := d.Info(); e == nil {
				total += info.Size()
			}
		}
		return nil
	})
	return total
}

// backupNames lists complete backups of base in dst, oldest first (".partial" dirs never match).
func backupNames(dst, base string) []string {
	re := regexp.MustCompile("^" + regexp.QuoteMeta(base) + `_\d{8}_\d{6}$`)
	entries, err := os.ReadDir(dst)
	if err != nil {
		return nil
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() && re.MatchString(e.Name()) {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	return names
}

// prune keeps only the newest `keep` backups of this source (keep <= 0 means unlimited).
func prune(dst, base string, keep int) {
	if keep <= 0 {
		return
	}
	names := backupNames(dst, base)
	for len(names) > keep {
		if err := os.RemoveAll(filepath.Join(dst, names[0])); err != nil {
			logf("❌ 오래된 백업 삭제 실패: %s (%v)", names[0], err)
		} else {
			logf("🗑 오래된 백업 삭제: %s", names[0])
		}
		names = names[1:]
	}
}

func runBackup(o *options) bool {
	base := filepath.Base(o.src)
	name := fmt.Sprintf("%s_%s", base, time.Now().Format("20060102_150405"))
	final := filepath.Join(o.dst, name)
	partial := final + ".partial"

	if _, err := os.Lstat(final); err == nil {
		logf("❌ 오류 발생: 이미 존재하는 백업입니다: %s", name)
		return false
	}
	prev := ""
	if o.incremental {
		if names := backupNames(o.dst, base); len(names) > 0 {
			prev = filepath.Join(o.dst, names[len(names)-1])
		}
	}

	st := &stats{}
	if !o.dryRun {
		if err := os.Mkdir(partial, 0o700); err != nil {
			logf("❌ 오류 발생: %v", err)
			return false
		}
	}
	if err := copyTree(o, st, o.src, partial, prev, ""); err != nil {
		if !o.dryRun {
			os.RemoveAll(partial)
		}
		logf("❌ 오류 발생: %v", err)
		return false
	}
	if o.dryRun {
		logf("🧪 [dry-run] 백업 계획: %s", name)
	} else {
		if err := os.Rename(partial, final); err != nil {
			os.RemoveAll(partial)
			logf("❌ 오류 발생: %v", err)
			return false
		}
		if o.verify {
			logf("🔍 검증 완료: %d개 파일 일치", st.verified)
		}
	}
	logf("📦 복사 %d개, 재사용 %d개, 제외 %d개", st.copied, st.reused, st.excluded)
	if st.skipped > 0 {
		logf("⚠ 심볼릭 링크/특수 파일 %d개는 건너뛰었습니다", st.skipped)
	}
	if !o.dryRun {
		logf("✅ 백업 완료: %s (폴더 용량: %s)", name, readableSize(float64(dirSize(o.dst))))
		prune(o.dst, base, o.keep)
	}
	return true
}

func usageError(msg string) {
	fmt.Fprintln(os.Stderr, msg)
	flag.Usage()
	os.Exit(2)
}

func main() {
	srcFlag := flag.String("source", "", "백업할 원본 폴더")
	dstFlag := flag.String("target", "", "백업을 저장할 폴더")
	intervalFlag := flag.String("interval", "5m", "백업 주기 (예: 30s, 5m, 1h)")
	keep := flag.Int("keep", 0, "보관할 최근 백업 개수 (0 = 무제한)")
	once := flag.Bool("once", false, "한 번만 백업하고 종료")
	mode := flag.String("mode", "full", "full | incremental (변경 없는 파일은 직전 백업에 하드링크)")
	var excludes stringList
	flag.Var(&excludes, "exclude", "제외할 글롭 패턴 (여러 번 지정 가능)")
	verify := flag.Bool("verify", false, "복사한 파일을 원본과 바이트 비교")
	dryRun := flag.Bool("dry-run", false, "아무것도 쓰지 않고 계획만 출력")
	logPath := flag.String("log-file", "", "로그를 추가로 저장할 파일")
	flag.Parse()

	if *srcFlag == "" || *dstFlag == "" {
		usageError("--source 와 --target 은 필수입니다.")
	}
	interval, err := parseInterval(*intervalFlag)
	if err != nil {
		usageError(err.Error())
	}
	if *keep < 0 {
		usageError("--keep 은 0 이상의 정수여야 합니다.")
	}
	if *mode != "full" && *mode != "incremental" {
		usageError(fmt.Sprintf("잘못된 모드: %q (full 또는 incremental)", *mode))
	}
	src, dst, err := validate(*srcFlag, *dstFlag)
	if err != nil {
		fmt.Fprintln(os.Stderr, "❌", err)
		os.Exit(1)
	}
	if *logPath != "" {
		logFile, err = os.OpenFile(*logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
		if err != nil {
			fmt.Fprintln(os.Stderr, "❌ 로그 파일을 열 수 없습니다:", err)
			os.Exit(1)
		}
		defer logFile.Close()
	}
	o := &options{src: src, dst: dst, keep: *keep, incremental: *mode == "incremental",
		excludes: excludes, verify: *verify, dryRun: *dryRun}

	if *once || *dryRun {
		if !runBackup(o) {
			logFile.Close()
			os.Exit(1)
		}
		return
	}

	logf("자동 백업 시작됨 (주기: %s)", *intervalFlag)
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	for {
		runBackup(o)
		select {
		case <-time.After(interval):
		case <-sig:
			logf("자동 백업이 사용자에 의해 중지되었습니다.")
			return
		}
	}
}
