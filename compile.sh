#!/bin/bash
mkdir -p docs/archive/bin
echo "Compiling for Mac ARM64..."
(cd docs/archive/golang && GOOS=darwin GOARCH=arm64 go build -o ../bin/peppol_mac_arm64 main.go)
echo "Compiling for Mac AMD64..."
(cd docs/archive/golang && GOOS=darwin GOARCH=amd64 go build -o ../bin/peppol_mac_amd64 main.go)
echo "Compiling for Linux AMD64..."
(cd docs/archive/golang && GOOS=linux GOARCH=amd64 go build -o ../bin/peppol_linux main.go)
echo "Done."