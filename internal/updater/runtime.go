package updater

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Runtime struct {
	HTTP     *http.Client
	ProcRoot string
}

func New() *Runtime {
	client := &http.Client{Timeout: 3 * time.Minute, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) > 5 {
			return errors.New("too many download redirects")
		}
		return trustedURL(req.URL)
	}}
	return &Runtime{HTTP: client, ProcRoot: "/proc"}
}
func trustedURL(u *url.URL) error {
	if u.Scheme != "https" || u.User != nil || u.Port() != "" {
		return errors.New("only credential-free HTTPS downloads are allowed")
	}
	host := u.Hostname()
	if host != "github.com" && host != "raw.githubusercontent.com" && host != "objects.githubusercontent.com" && host != "release-assets.githubusercontent.com" {
		return fmt.Errorf("untrusted download host: %s", host)
	}
	return nil
}
func (r *Runtime) get(raw string) (*http.Response, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return nil, err
	}
	if err = trustedURL(u); err != nil {
		return nil, err
	}
	req, err := http.NewRequest(http.MethodGet, raw, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "amp-wart-update/0.1.0")
	response, err := r.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	if response.StatusCode != http.StatusOK {
		response.Body.Close()
		return nil, fmt.Errorf("download returned HTTP %d", response.StatusCode)
	}
	return response, nil
}
func (r *Runtime) channel(b Binding) (Manifest, error) {
	var m Manifest
	response, err := r.get(b.ChannelURL)
	if err != nil {
		return m, err
	}
	defer response.Body.Close()
	if response.ContentLength > 1<<20 {
		return m, errors.New("channel manifest is too large")
	}
	if err = decode(io.LimitReader(response.Body, (1<<20)+1), &m); err != nil {
		return m, err
	}
	return m, validate(m, b, true)
}
func (r *Runtime) stopped(binary string) error {
	target, err := os.Stat(binary)
	if err != nil {
		return err
	}
	entries, err := os.ReadDir(r.ProcRoot)
	if err != nil {
		return fmt.Errorf("cannot inspect Linux process state: %w", err)
	}
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil || pid == os.Getpid() {
			continue
		}
		executable, err := os.Stat(filepath.Join(r.ProcRoot, entry.Name(), "exe"))
		if err != nil {
			continue
		}
		if os.SameFile(target, executable) {
			return errors.New("stop the node application in AMP before Update or rollback; leave ADS and the managed AMP panel running")
		}
	}
	return nil
}
func (r *Runtime) prepare(root, network string) (string, Binding, Selection, error) {
	root, err := rootPath(root)
	if err != nil {
		return root, Binding{}, Selection{}, err
	}
	b, err := readBinding(root, network)
	if err != nil {
		return root, b, Selection{}, err
	}
	s, err := selection(root, "current", b)
	return root, b, s, err
}
func result(action string, s Selection, changed bool) Result {
	return Result{Action: action, Network: s.Manifest.Network, Version: s.Manifest.Version, SourceCommit: s.Manifest.SourceCommit, SHA256: s.Manifest.Binary.SHA256, Changed: changed}
}
func (r *Runtime) Verify(root, network string) (Result, error) {
	_, _, s, err := r.prepare(root, network)
	if err != nil {
		return Result{}, err
	}
	return result("verify", s, false), nil
}
func (r *Runtime) Check(root, network string) (Result, error) {
	_, b, current, err := r.prepare(root, network)
	if err != nil {
		return Result{}, err
	}
	m, err := r.channel(b)
	if err != nil {
		return Result{}, err
	}
	if m.Sequence < current.Manifest.Sequence {
		return Result{}, errors.New("channel sequence is older than the selected release; explicit rollback is required")
	}
	return result("check", Selection{Manifest: m}, m.Binary.SHA256 != current.Manifest.Binary.SHA256), nil
}
func (r *Runtime) download(root string, m Manifest) (string, error) {
	final := filepath.Join(root, "releases", m.Binary.SHA256)
	if _, err := os.Lstat(final); err == nil {
		var existing Manifest
		if err = readJSON(filepath.Join(final, "amp-release.json"), &existing); err != nil {
			return "", err
		}
		comparable := existing
		comparable.Sequence = m.Sequence
		if comparable != m {
			return "", errors.New("existing release metadata differs from the published release")
		}
		return final, verifyRelease(final, m)
	} else if !os.IsNotExist(err) {
		return "", err
	}
	stage, err := os.MkdirTemp(filepath.Join(root, "releases"), ".download-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(stage)
	response, err := r.get(m.Binary.URL)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.ContentLength >= 0 && response.ContentLength != m.Binary.Size {
		return "", errors.New("download content length differs from the published size")
	}
	binary := filepath.Join(stage, "wart-node")
	file, err := os.OpenFile(binary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0755)
	if err != nil {
		return "", err
	}
	size, err := io.Copy(file, io.LimitReader(response.Body, m.Binary.Size+1))
	if err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		return "", err
	}
	if size != m.Binary.Size {
		return "", errors.New("incomplete or oversized binary download")
	}
	if err = writeFile(filepath.Join(stage, "SHA256SUMS"), []byte(m.Binary.SHA256+"  wart-node\n"), 0644); err != nil {
		return "", err
	}
	if err = writeJSON(filepath.Join(stage, "amp-release.json"), m); err != nil {
		return "", err
	}
	if err = writeFile(filepath.Join(stage, "BUILD.txt"), []byte("Warthog "+m.Network+" "+m.Version+"\nSource: "+m.SourceCommit+"\nEpoch: "+m.Epoch+"\nSHA-256: "+m.Binary.SHA256+"\n"), 0644); err != nil {
		return "", err
	}
	if err = verifyRelease(stage, m); err != nil {
		return "", err
	}
	if err = os.Rename(stage, final); err != nil {
		return "", err
	}
	return final, syncDir(filepath.Join(root, "releases"))
}
func (r *Runtime) Update(root, network string) (Result, error) {
	root, err := rootPath(root)
	if err != nil {
		return Result{}, err
	}
	unlock, err := lock(root)
	if err != nil {
		return Result{}, err
	}
	defer unlock()
	root, b, current, err := r.prepare(root, network)
	if err != nil {
		return Result{}, err
	}
	m, err := r.channel(b)
	if err != nil {
		return Result{}, err
	}
	if m.Sequence < current.Manifest.Sequence {
		return Result{}, errors.New("channel sequence is older than the selected release; use explicit rollback")
	}
	if m.Binary.SHA256 == current.Manifest.Binary.SHA256 {
		return result("update", current, false), nil
	}
	if err = r.stopped(filepath.Join(current.Directory, "wart-node")); err != nil {
		return Result{}, err
	}
	if _, err = r.download(root, m); err != nil {
		return Result{}, err
	}
	latest, err := selection(root, "current", b)
	if err != nil {
		return Result{}, err
	}
	if latest.Target != current.Target {
		return Result{}, errors.New("current selection changed during download")
	}
	if err = r.stopped(filepath.Join(current.Directory, "wart-node")); err != nil {
		return Result{}, err
	}
	if err = replaceLink(root, "previous", current.Target); err != nil {
		return Result{}, err
	}
	target := "releases/" + m.Binary.SHA256
	if err = replaceLink(root, "current", target); err != nil {
		return Result{}, err
	}
	return result("update", Selection{Manifest: m}, true), nil
}
func (r *Runtime) Rollback(root, network string) (Result, error) {
	root, err := rootPath(root)
	if err != nil {
		return Result{}, err
	}
	unlock, err := lock(root)
	if err != nil {
		return Result{}, err
	}
	defer unlock()
	root, b, current, err := r.prepare(root, network)
	if err != nil {
		return Result{}, err
	}
	previous, err := selection(root, "previous", b)
	if err != nil {
		return Result{}, err
	}
	if current.Target == previous.Target {
		return result("rollback", current, false), nil
	}
	if err = r.stopped(filepath.Join(current.Directory, "wart-node")); err != nil {
		return Result{}, err
	}
	// Keep previous pointing at the rollback release so repeated rollback is idempotent.
	if err = replaceLink(root, "current", previous.Target); err != nil {
		return Result{}, err
	}
	return result("rollback", previous, true), nil
}

// URL validation is also exposed to the preparation tests, without an insecure HTTP mode.
func ValidateArtifactURL(raw string) error {
	u, err := url.Parse(raw)
	if err != nil {
		return err
	}
	if strings.Contains(raw, "\\") {
		return errors.New("invalid URL")
	}
	return trustedURL(u)
}
