package updater

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

type roundTrip func(*http.Request) (*http.Response, error)

func (f roundTrip) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }
func payload(label string) []byte {
	data := make([]byte, 64)
	copy(data, []byte{0x7f, 'E', 'L', 'F', 2, 1, 1})
	binary.LittleEndian.PutUint16(data[16:], 2)
	binary.LittleEndian.PutUint16(data[18:], 62)
	binary.LittleEndian.PutUint32(data[20:], 1)
	binary.LittleEndian.PutUint16(data[52:], 64)
	binary.LittleEndian.PutUint16(data[54:], 56)
	return append(data, []byte(label)...)
}
func hash(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }
func put(t *testing.T, path string, data []byte, mode os.FileMode) {
	t.Helper()
	if err := os.WriteFile(path, data, mode); err != nil {
		t.Fatal(err)
	}
}
func fixture(t *testing.T) (string, Binding, Manifest, []byte) {
	t.Helper()
	base := t.TempDir()
	root := filepath.Join(base, "application with spaces")
	os.MkdirAll(filepath.Join(root, "releases"), 0755)
	b := Binding{Schema: 1, Network: "mainnet", ChainID: strings.Repeat("a", 64), Epoch: "mainnet-v1", ChannelURL: "https://raw.githubusercontent.com/" + Repository + "/main/channels/mainnet.json"}
	data := payload("old fixture")
	m := Manifest{Schema: 1, Network: b.Network, Platform: "linux-amd64", Version: "0.8.20", SourceCommit: strings.Repeat("1", 40), ChainID: b.ChainID, Epoch: b.Epoch, Sequence: 1, Binary: Artifact{SHA256: hash(data), Size: int64(len(data))}}
	dir := filepath.Join(root, "releases", m.Binary.SHA256)
	os.Mkdir(dir, 0755)
	put(t, filepath.Join(dir, "wart-node"), data, 0755)
	put(t, filepath.Join(dir, "SHA256SUMS"), []byte(m.Binary.SHA256+"  wart-node\n"), 0644)
	if err := writeJSON(filepath.Join(dir, "amp-release.json"), m); err != nil {
		t.Fatal(err)
	}
	if err := writeJSON(filepath.Join(root, "amp-update.json"), b); err != nil {
		t.Fatal(err)
	}
	os.Symlink("releases/"+m.Binary.SHA256, filepath.Join(root, "current"))
	os.Mkdir(filepath.Join(root, "data"), 0755)
	for _, name := range []string{"chain.db3", "chain.db3-wal", "chain.db3-shm", "peers.db3"} {
		put(t, filepath.Join(root, "data", name), []byte("retained database bytes\x00\xff"), 0600)
	}
	put(t, filepath.Join(base, "GenericModule.kvp"), []byte("flags and minfee must stay unchanged\r\n"), 0600)
	return root, b, m, data
}
func candidate(old Manifest) (Manifest, []byte) {
	m := old
	data := payload("new static fixture")
	m.SourceCommit = strings.Repeat("2", 40)
	m.Sequence = 2
	m.Binary = Artifact{URL: "https://github.com/" + Repository + "/releases/download/mainnet-example/wart-node-mainnet-linux-amd64", SHA256: hash(data), Size: int64(len(data))}
	return m, data
}
func runtimeFor(t *testing.T, b Binding, m Manifest, data []byte) (*Runtime, *int) {
	t.Helper()
	count := new(int)
	raw, _ := json.Marshal(m)
	proc := t.TempDir()
	client := &http.Client{Transport: roundTrip(func(req *http.Request) (*http.Response, error) {
		if req.Header.Get("Authorization") != "" {
			t.Fatal("unexpected credential transmission")
		}
		switch req.URL.String() {
		case b.ChannelURL:
			return &http.Response{StatusCode: 200, Body: io.NopCloser(bytes.NewReader(raw)), ContentLength: int64(len(raw)), Header: make(http.Header)}, nil
		case m.Binary.URL:
			*count++
			return &http.Response{StatusCode: 200, Body: io.NopCloser(bytes.NewReader(data)), ContentLength: int64(len(data)), Header: make(http.Header)}, nil
		}
		return nil, fmt.Errorf("unexpected download: %s", req.URL)
	})}
	return &Runtime{HTTP: client, ProcRoot: proc}, count
}
func snapshot(t *testing.T, root string) map[string]string {
	t.Helper()
	result := map[string]string{}
	filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			t.Fatal(err)
		}
		name, _ := filepath.Rel(root, path)
		if d.Type()&os.ModeSymlink != 0 {
			target, _ := os.Readlink(path)
			result[name] = "link:" + target
		} else if !d.IsDir() {
			data, _ := os.ReadFile(path)
			result[name] = hash(data)
		}
		return nil
	})
	return result
}
func currentTarget(t *testing.T, root string) string {
	t.Helper()
	target, err := os.Readlink(filepath.Join(root, "current"))
	if err != nil {
		t.Fatal(err)
	}
	return target
}
func TestUpdateVerifyRollbackAndRetention(t *testing.T) {
	root, b, old, _ := fixture(t)
	m, data := candidate(old)
	r, count := runtimeFor(t, b, m, data)
	dbBefore := snapshot(t, filepath.Join(root, "data"))
	config := filepath.Join(filepath.Dir(root), "GenericModule.kvp")
	configBefore, _ := os.ReadFile(config)
	if result, err := r.Update(root, b.Network); err != nil || !result.Changed {
		t.Fatalf("%+v %v", result, err)
	}
	if *count != 1 || currentTarget(t, root) != "releases/"+m.Binary.SHA256 {
		t.Fatal("wrong selection")
	}
	if !reflect.DeepEqual(dbBefore, snapshot(t, filepath.Join(root, "data"))) {
		t.Fatal("database modified")
	}
	now, _ := os.ReadFile(config)
	if !bytes.Equal(now, configBefore) {
		t.Fatal("configuration modified")
	}
	if _, err := os.Stat(filepath.Join(root, "releases", old.Binary.SHA256, "wart-node")); err != nil {
		t.Fatal("old build removed")
	}
	r.HTTP = nil // Offline startup verification must not contact the channel.
	if _, err := r.Verify(root, b.Network); err != nil {
		t.Fatal(err)
	}
	r, _ = runtimeFor(t, b, m, data)
	if result, err := r.Update(root, b.Network); err != nil || result.Changed {
		t.Fatalf("repeat: %+v %v", result, err)
	}
	r.HTTP = nil
	if result, err := r.Rollback(root, b.Network); err != nil || !result.Changed {
		t.Fatalf("rollback: %+v %v", result, err)
	}
	if currentTarget(t, root) != "releases/"+old.Binary.SHA256 {
		t.Fatal("rollback failed")
	}
	if result, err := r.Rollback(root, b.Network); err != nil || result.Changed {
		t.Fatalf("repeat rollback: %+v %v", result, err)
	}
	if !reflect.DeepEqual(dbBefore, snapshot(t, filepath.Join(root, "data"))) {
		t.Fatal("rollback changed database")
	}
}
func TestCheckWritesNothing(t *testing.T) {
	root, b, old, _ := fixture(t)
	m, data := candidate(old)
	r, _ := runtimeFor(t, b, m, data)
	before := snapshot(t, root)
	if result, err := r.Check(root, b.Network); err != nil || !result.Changed {
		t.Fatalf("%+v %v", result, err)
	}
	if !reflect.DeepEqual(before, snapshot(t, root)) {
		t.Fatal("check wrote files")
	}
}
func TestRejectNetworkEpochAndSequence(t *testing.T) {
	for _, kind := range []string{"network", "chain", "epoch", "sequence", "host", "repository", "oversized", "unknown schema"} {
		t.Run(kind, func(t *testing.T) {
			root, b, old, _ := fixture(t)
			m, data := candidate(old)
			switch kind {
			case "network":
				m.Network = "testnet"
			case "chain":
				m.ChainID = strings.Repeat("b", 64)
			case "epoch":
				m.Epoch = "reset-unapproved"
			case "sequence":
				m.Sequence = 0
			case "host":
				m.Binary.URL = "https://evil.invalid/node"
			case "repository":
				m.Binary.URL = "https://github.com/other/repo/releases/download/x/node"
			case "oversized":
				m.Binary.Size = MaxBinary + 1
			case "unknown schema":
				m.Schema = 2
			}
			r, count := runtimeFor(t, b, m, data)
			before := currentTarget(t, root)
			if _, err := r.Update(root, b.Network); err == nil {
				t.Fatal("unsafe release accepted")
			}
			if *count != 0 || currentTarget(t, root) != before {
				t.Fatal("unsafe release downloaded/selected")
			}
		})
	}
}
func TestFailedDownloadKeepsOldRelease(t *testing.T) {
	for _, kind := range []string{"checksum", "size", "not ELF", "HTTP failure"} {
		t.Run(kind, func(t *testing.T) {
			root, b, old, _ := fixture(t)
			m, data := candidate(old)
			switch kind {
			case "checksum":
				m.Binary.SHA256 = strings.Repeat("b", 64)
			case "size":
				m.Binary.Size++
			case "not ELF":
				data = []byte("not a node executable")
				m.Binary.SHA256 = hash(data)
				m.Binary.Size = int64(len(data))
			}
			r, _ := runtimeFor(t, b, m, data)
			if kind == "HTTP failure" {
				base := r.HTTP.Transport
				r.HTTP.Transport = roundTrip(func(req *http.Request) (*http.Response, error) {
					if req.URL.String() == m.Binary.URL {
						return nil, io.ErrUnexpectedEOF
					}
					return base.RoundTrip(req)
				})
			}
			before := currentTarget(t, root)
			db := snapshot(t, filepath.Join(root, "data"))
			if _, err := r.Update(root, b.Network); err == nil {
				t.Fatal("failed download accepted")
			}
			if currentTarget(t, root) != before || !reflect.DeepEqual(db, snapshot(t, filepath.Join(root, "data"))) {
				t.Fatal("failure changed current/data")
			}
			entries, _ := os.ReadDir(filepath.Join(root, "releases"))
			for _, e := range entries {
				if strings.HasPrefix(e.Name(), ".download-") {
					t.Fatal("partial download left behind")
				}
			}
		})
	}
}
func TestNodeRunningBlocksButAMPPanelDoesNot(t *testing.T) {
	root, b, old, _ := fixture(t)
	m, data := candidate(old)
	r, count := runtimeFor(t, b, m, data)
	proc := filepath.Join(r.ProcRoot, "999998")
	os.Mkdir(proc, 0755)
	amp := filepath.Join(t.TempDir(), "AMP_Linux_x86_64")
	put(t, amp, []byte("AMP fixture"), 0755)
	os.Symlink(amp, filepath.Join(proc, "exe"))
	os.Symlink(filepath.Dir(root), filepath.Join(proc, "cwd"))
	node := filepath.Join(r.ProcRoot, "999997")
	os.Mkdir(node, 0755)
	os.Symlink(filepath.Join(root, "current", "wart-node"), filepath.Join(node, "exe"))
	if _, err := r.Update(root, b.Network); err == nil || !strings.Contains(err.Error(), "stop the node") {
		t.Fatalf("running node not blocked: %v", err)
	}
	if *count != 0 {
		t.Fatal("downloaded while node running")
	}
	os.Remove(filepath.Join(node, "exe"))
	if _, err := r.Update(root, b.Network); err != nil {
		t.Fatalf("running AMP panel blocked update: %v", err)
	}
}
func TestExclusiveLock(t *testing.T) {
	root, b, old, _ := fixture(t)
	m, data := candidate(old)
	r, _ := runtimeFor(t, b, m, data)
	unlock, err := lock(root)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	if _, err = r.Update(root, b.Network); err == nil || !strings.Contains(err.Error(), "already running") {
		t.Fatalf("lock failed: %v", err)
	}
}
func TestUnsafeLinksAndCorruptionFailClosed(t *testing.T) {
	for _, kind := range []string{"current escape", "binary symlink", "binding symlink", "corrupt installed", "physical previous"} {
		t.Run(kind, func(t *testing.T) {
			root, b, old, _ := fixture(t)
			m, data := candidate(old)
			r, _ := runtimeFor(t, b, m, data)
			switch kind {
			case "current escape":
				os.Remove(filepath.Join(root, "current"))
				os.Symlink(t.TempDir(), filepath.Join(root, "current"))
			case "binary symlink":
				p := filepath.Join(root, "current", "wart-node")
				os.Remove(p)
				outside := filepath.Join(t.TempDir(), "node")
				put(t, outside, payload("old fixture"), 0755)
				os.Symlink(outside, p)
			case "binding symlink":
				p := filepath.Join(root, "amp-update.json")
				content, _ := os.ReadFile(p)
				os.Remove(p)
				outside := filepath.Join(t.TempDir(), "binding")
				put(t, outside, content, 0644)
				os.Symlink(outside, p)
			case "corrupt installed":
				put(t, filepath.Join(root, "current", "wart-node"), []byte("corrupt"), 0755)
			case "physical previous":
				os.Mkdir(filepath.Join(root, "previous"), 0755)
			}
			before := currentTarget(t, root)
			if _, err := r.Update(root, b.Network); err == nil {
				t.Fatal("unsafe setup accepted")
			}
			if currentTarget(t, root) != before {
				t.Fatal("current selection changed")
			}
		})
	}
}
func TestOfflineVerifyRejectsCorruption(t *testing.T) {
	root, b, _, _ := fixture(t)
	put(t, filepath.Join(root, "current", "wart-node"), []byte("bad"), 0755)
	r := New()
	r.HTTP = nil
	if _, err := r.Verify(root, b.Network); err == nil {
		t.Fatal("corrupt node passed startup verification")
	}
}
func TestStrictManifestAndTLSURLs(t *testing.T) {
	for _, raw := range []string{`{"schema":1,"unexpected":true}`, `{} {}`} {
		var m Manifest
		if err := decode(strings.NewReader(raw), &m); err == nil {
			t.Fatal("invalid JSON accepted")
		}
	}
	for _, raw := range []string{"http://github.com/a", "https://user:secret@github.com/a", "https://github.com:444/a", "https://localhost/a", "https://github.com.evil.invalid/a"} {
		if err := ValidateArtifactURL(raw); err == nil {
			t.Fatal("untrusted URL accepted", raw)
		}
	}
}

func TestPositiveOlderSequenceCannotDowngrade(t *testing.T) {
	root, b, old, _ := fixture(t)
	m, data := candidate(old)
	old.Sequence = 3
	encoded, _ := json.Marshal(old)
	put(t, filepath.Join(root, "current", "amp-release.json"), encoded, 0644)
	r, count := runtimeFor(t, b, m, data)
	before := currentTarget(t, root)
	if _, err := r.Update(root, b.Network); err == nil || !strings.Contains(err.Error(), "older") {
		t.Fatalf("downgrade not blocked: %v", err)
	}
	if *count != 0 || currentTarget(t, root) != before {
		t.Fatal("downgrade changed selection")
	}
}
