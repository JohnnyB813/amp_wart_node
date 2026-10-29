package main

import (
	"fmt"
	"github.com/JohnnyB813/amp_wart_node/internal/updater"
	"os"
)

func main() {
	if err := updater.Run(os.Args[1:], os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "AMP Warthog update stopped:", err)
		os.Exit(1)
	}
}
