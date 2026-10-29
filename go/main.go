package main

import (
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

// parseInterval accepts "30s", "1m", "1h" (number + unit).
func parseInterval(s string) (time.Duration, error) {
	if len(s) < 2 {
		return 0, fmt.Errorf("잘못된 주기: %q (예: 30s, 5m, 1h)", s)
	}
	n, err := strconv.Atoi(s[:len(s)-1])
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("잘못된 주기: %q (예: 30s, 5m, 1h)", s)
	}
	switch s[len(s)-1] {
	case 's':
		return time.Duration(n) * time.Second, nil
	case 'm':
		return time.Duration(n) * time.Minute, nil
	case 'h':
		return time.Duration(n) * time.Hour, nil
	}
	return 0, fmt.Errorf("잘못된 주기: %q (예: 30s, 5m, 1h)", s)
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

func copyDir(src, dst string) (skipped int, err error) {
	err = filepath.WalkDir(src, func(p string, d fs.DirEntry, werr error) error {
		if werr != nil {
			return werr
		}
		rel, _ := filepath.Rel(src, p)
		out := filepath.Join(dst, rel)
		info, err := d.Info()
		if err != nil {
			return err
		}
		switch {
		case d.IsDir():
			return os.MkdirAll(out, info.Mode().Perm()|0o700)
		case info.Mode()&fs.ModeSymlink != 0, !info.Mode().IsRegular():
			skipped++
			return nil
		}
		return copyFile(p, out, info.Mode().Perm())
	})
	return skipped, err
}

func copyFile(src, dst string, mode fs.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
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

// prune keeps only the newest `keep` backups of this source (keep <= 0 means unlimited).
func prune(dst, base string, keep int) {
	if keep <= 0 {
		return
	}
	re := regexp.MustCompile("^" + regexp.QuoteMeta(base) + `_\d{8}_\d{6}$`)
	entries, err := os.ReadDir(dst)
	if err != nil {
		return
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() && re.MatchString(e.Name()) {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for len(names) > keep {
		if err := os.RemoveAll(filepath.Join(dst, names[0])); err != nil {
			logf("❌ 오래된 백업 삭제 실패: %s (%v)", names[0], err)
		} else {
			logf("🗑 오래된 백업 삭제: %s", names[0])
		}
		names = names[1:]
	}
}

func runBackup(src, dst string, keep int) {
	base := filepath.Base(src)
	name := fmt.Sprintf("%s_%s", base, time.Now().Format("20060102_150405"))
	target := filepath.Join(dst, name)
	skipped, err := copyDir(src, target)
	if err != nil {
		logf("❌ 오류 발생: %v", err)
		return
	}
	logf("✅ 백업 완료: %s (폴더 용량: %s)", name, readableSize(float64(dirSize(dst))))
	if skipped > 0 {
		logf("⚠ 심볼릭 링크/특수 파일 %d개는 건너뛰었습니다", skipped)
	}
	prune(dst, base, keep)
}

func main() {
	srcFlag := flag.String("source", "", "백업할 원본 폴더")
	dstFlag := flag.String("target", "", "백업을 저장할 폴더")
	intervalFlag := flag.String("interval", "5m", "백업 주기 (예: 30s, 5m, 1h)")
	keep := flag.Int("keep", 0, "보관할 최근 백업 개수 (0 = 무제한)")
	once := flag.Bool("once", false, "한 번만 백업하고 종료")
	logPath := flag.String("log-file", "", "로그를 추가로 저장할 파일")
	flag.Parse()

	if *srcFlag == "" || *dstFlag == "" {
		fmt.Fprintln(os.Stderr, "--source 와 --target 은 필수입니다.")
		flag.Usage()
		os.Exit(2)
	}
	interval, err := parseInterval(*intervalFlag)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
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

	if *once {
		runBackup(src, dst, *keep)
		return
	}

	logf("자동 백업 시작됨 (주기: %s)", *intervalFlag)
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)
	for {
		runBackup(src, dst, *keep)
		select {
		case <-time.After(interval):
		case <-sig:
			logf("자동 백업이 사용자에 의해 중지되었습니다.")
			return
		}
	}
}
