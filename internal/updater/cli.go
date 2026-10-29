package updater

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
)

const Version = "0.1.0"

func Run(args []string, out io.Writer) error {
	if len(args) == 1 && (args[0] == "version" || args[0] == "--version") {
		fmt.Fprintln(out, Version)
		return nil
	}
	if len(args) == 0 {
		return fmt.Errorf("usage: amp-wart-update {check|update|verify|rollback} --root /application/root --network {mainnet|testnet}")
	}
	action := args[0]
	flags := flag.NewFlagSet(action, flag.ContinueOnError)
	flags.SetOutput(out)
	root := flags.String("root", "", "absolute application directory")
	network := flags.String("network", "", "mainnet or testnet")
	if err := flags.Parse(args[1:]); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments")
	}
	r := New()
	var result Result
	var err error
	switch action {
	case "check":
		result, err = r.Check(*root, *network)
	case "update":
		result, err = r.Update(*root, *network)
	case "verify":
		result, err = r.Verify(*root, *network)
	case "rollback":
		result, err = r.Rollback(*root, *network)
	default:
		return fmt.Errorf("unknown action: %s", action)
	}
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(out)
	encoder.SetIndent("", "  ")
	return encoder.Encode(result)
}
