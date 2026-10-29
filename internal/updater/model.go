// Package updater implements checksum-verified, epoch-bound AMP node updates.
// It never opens chain databases, edits launch flags, or starts/stops services.
package updater

import (
	"crypto/sha256"
	"debug/elf"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
)

const Repository = "JohnnyB813/amp_wart_node"
const MaxBinary = 64 << 20

var hashPattern = regexp.MustCompile(`^[a-f0-9]{64}$`)
var commitPattern = regexp.MustCompile(`^[a-f0-9]{40}$`)
var epochPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,63}$`)
var versionPattern = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)

type Binding struct {
	Schema     int    `json:"schema"`
	Network    string `json:"network"`
	ChainID    string `json:"chain_id"`
	Epoch      string `json:"epoch"`
	ChannelURL string `json:"channel_url"`
}
type Artifact struct {
	URL    string `json:"url"`
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}
type Manifest struct {
	Schema       int      `json:"schema"`
	Network      string   `json:"network"`
	Platform     string   `json:"platform"`
	Version      string   `json:"version"`
	SourceCommit string   `json:"source_commit"`
	ChainID      string   `json:"chain_id"`
	Epoch        string   `json:"epoch"`
	Sequence     int64    `json:"sequence"`
	Binary       Artifact `json:"binary"`
}
type Selection struct {
	Target    string
	Directory string
	Manifest  Manifest
}
type Result struct {
	Action                string `json:"action"`
	Network               string `json:"network"`
	Version               string `json:"version"`
	SourceCommit          string `json:"source_commit"`
	SHA256                string `json:"sha256"`
	Changed               bool   `json:"changed"`
	DataModified          bool   `json:"data_modified"`
	ConfigurationModified bool   `json:"configuration_modified"`
}

func decode(reader io.Reader, value any) error {
	d := json.NewDecoder(reader)
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		return err
	}
	var extra any
	if err := d.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("unexpected trailing JSON")
	}
	return nil
}
func readJSON(path string, value any) error {
	if err := regular(path); err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return decode(io.LimitReader(f, 1<<20), value)
}
func regular(path string) error {
	st, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !st.Mode().IsRegular() {
		return fmt.Errorf("expected regular non-symlink file: %s", path)
	}
	return nil
}
func directory(path string) error {
	st, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("expected non-symlink directory: %s", path)
	}
	return nil
}
func rootPath(root string) (string, error) {
	if !filepath.IsAbs(root) {
		return "", errors.New("use the absolute application root")
	}
	root = filepath.Clean(root)
	if err := directory(root); err != nil {
		return "", err
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	if resolved != root {
		return "", errors.New("application root contains a symlink")
	}
	return root, nil
}
func readBinding(root, network string) (Binding, error) {
	var b Binding
	if err := readJSON(filepath.Join(root, "amp-update.json"), &b); err != nil {
		return b, err
	}
	if b.Schema != 1 || b.Network != network || (network != "mainnet" && network != "testnet") || !hashPattern.MatchString(b.ChainID) || !epochPattern.MatchString(b.Epoch) {
		return b, errors.New("invalid or wrong-network updater binding")
	}
	expected := "https://raw.githubusercontent.com/" + Repository + "/main/channels/" + network + ".json"
	if b.ChannelURL != expected {
		return b, errors.New("unexpected channel URL")
	}
	return b, nil
}
func validate(m Manifest, b Binding, remote bool) error {
	if m.Schema != 1 || m.Platform != "linux-amd64" || m.Network != b.Network {
		return errors.New("manifest schema/platform/network mismatch")
	}
	if !versionPattern.MatchString(m.Version) || !commitPattern.MatchString(m.SourceCommit) || !hashPattern.MatchString(m.ChainID) || !epochPattern.MatchString(m.Epoch) || !hashPattern.MatchString(m.Binary.SHA256) || m.Binary.Size < 1 || m.Binary.Size > MaxBinary || m.Sequence < 0 {
		return errors.New("invalid release manifest")
	}
	if m.ChainID != b.ChainID || m.Epoch != b.Epoch {
		return fmt.Errorf("RESET REQUIRED: channel epoch %s differs from installed %s; updates are blocked until an explicit migration after a full cold backup", m.Epoch, b.Epoch)
	}
	if remote {
		prefix := "https://github.com/" + Repository + "/releases/download/"
		if !strings.HasPrefix(m.Binary.URL, prefix) || strings.ContainsAny(strings.TrimPrefix(m.Binary.URL, prefix), "?#") || strings.Contains(m.Binary.URL, "/../") {
			return errors.New("binary URL is outside this repository's release assets")
		}
		if m.Sequence < 1 {
			return errors.New("published manifest requires a positive sequence")
		}
	}
	return nil
}
func digest(path string) (string, error) {
	if err := regular(path); err != nil {
		return "", err
	}
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err = io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
func verifyELF(path string) error {
	f, err := elf.Open(path)
	if err != nil {
		return fmt.Errorf("invalid ELF: %w", err)
	}
	defer f.Close()
	if f.Class != elf.ELFCLASS64 || f.Machine != elf.EM_X86_64 || f.Data != elf.ELFDATA2LSB {
		return errors.New("binary is not Linux x86-64 ELF")
	}
	for _, p := range f.Progs {
		if p.Type == elf.PT_INTERP {
			return errors.New("node executable requires a dynamic interpreter")
		}
	}
	libs, err := f.ImportedLibraries()
	if err != nil {
		return err
	}
	if len(libs) != 0 {
		return errors.New("node executable requires dynamic libraries")
	}
	return nil
}
func verifyRelease(dir string, m Manifest) error {
	if err := directory(dir); err != nil {
		return err
	}
	file := filepath.Join(dir, "wart-node")
	h, err := digest(file)
	if err != nil {
		return err
	}
	if h != m.Binary.SHA256 {
		return errors.New("installed executable SHA-256 mismatch")
	}
	st, err := os.Stat(file)
	if err != nil {
		return err
	}
	if st.Size() != m.Binary.Size || st.Mode().Perm()&0111 == 0 {
		return errors.New("installed executable size/mode mismatch")
	}
	if err = verifyELF(file); err != nil {
		return err
	}
	sums := filepath.Join(dir, "SHA256SUMS")
	if err = regular(sums); err != nil {
		return err
	}
	data, err := os.ReadFile(sums)
	if err != nil {
		return err
	}
	if string(data) != h+"  wart-node\n" {
		return errors.New("installed SHA256SUMS mismatch")
	}
	return nil
}
func selection(root, name string, b Binding) (Selection, error) {
	var s Selection
	target, err := os.Readlink(filepath.Join(root, name))
	if err != nil {
		return s, fmt.Errorf("%s must be a managed release symlink: %w", name, err)
	}
	parts := strings.Split(filepath.ToSlash(target), "/")
	if len(parts) != 2 || parts[0] != "releases" || !hashPattern.MatchString(parts[1]) {
		return s, errors.New("release link points outside releases/<sha256>")
	}
	if err = directory(filepath.Join(root, "releases")); err != nil {
		return s, err
	}
	s.Target = target
	s.Directory = filepath.Join(root, target)
	if err = readJSON(filepath.Join(s.Directory, "amp-release.json"), &s.Manifest); err != nil {
		return s, err
	}
	if err = validate(s.Manifest, b, false); err != nil {
		return s, err
	}
	if parts[1] != s.Manifest.Binary.SHA256 {
		return s, errors.New("release directory does not match its hash")
	}
	return s, verifyRelease(s.Directory, s.Manifest)
}
func writeFile(path string, data []byte, mode os.FileMode) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	if _, err = f.Write(data); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	return closeErr
}
func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return writeFile(path, append(data, '\n'), 0644)
}
func syncDir(root string) error {
	f, err := os.Open(root)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}
func replaceLink(root, name, target string) error {
	if name != "current" && name != "previous" {
		return errors.New("invalid selection name")
	}
	if st, err := os.Lstat(filepath.Join(root, name)); err == nil && st.Mode()&os.ModeSymlink == 0 {
		return errors.New("refusing to overwrite a non-symlink selection")
	}
	f, err := os.CreateTemp(root, ".select-")
	if err != nil {
		return err
	}
	temp := f.Name()
	f.Close()
	os.Remove(temp)
	defer os.Remove(temp)
	if err = os.Symlink(target, temp); err != nil {
		return err
	}
	if err = os.Rename(temp, filepath.Join(root, name)); err != nil {
		return err
	}
	return syncDir(root)
}
func lock(root string) (func(), error) {
	f, err := os.OpenFile(filepath.Join(root, ".amp-update.lock"), os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, err
	}
	if err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, errors.New("another updater is already running")
	}
	return func() { syscall.Flock(int(f.Fd()), syscall.LOCK_UN); f.Close() }, nil
}
