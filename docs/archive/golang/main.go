package main

import (
	"bytes"
	"encoding/xml"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/pflag"
)

// ... (flag definitions and main function remain the same) ...

var (
	tempDir        string
	force          bool
	cleanupBefore  bool
	cleanupAfter   bool
	maxBytes       int
	verbose        bool
	silent         bool
)

// BusinessCard represents the <businesscard> element
type BusinessCardRaw struct {
	XMLName  xml.Name
	InnerXML []byte `xml:",innerxml"`
}

func main() {
	// Define flags
	pflag.BoolVarP(&verbose, "verbose", "V", false, "Enable verbose output")
	pflag.BoolVarP(&silent, "silent", "S", false, "Suppress all output except for errors")
	pflag.BoolVarP(&force, "force", "F", false, "Force re-download of the XML file")
	pflag.BoolVarP(&cleanupBefore, "cleanup-before", "C", false, "Delete all existing XML files in extracts/ before starting")
	pflag.BoolVarP(&cleanupAfter, "cleanup-after", "A", false, "Clean up temporary files after processing")
	pflag.StringVarP(&tempDir, "temp-dir", "T", "tmp", "Temporary directory")
	pflag.IntVarP(&maxBytes, "max-bytes", "B", 1000000, "Maximum number of bytes per output file")

	// Parse flags
	pflag.Parse()

	if err := run(); err != nil {
		if !silent {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		}
		log.Printf("FATAL: %v", err)
		os.Exit(1)
	}
}

func run() error {
	// Create temp and extracts directories
	if err := os.MkdirAll(tempDir, os.ModePerm); err != nil {
		return err
	}
	if err := os.MkdirAll("extracts", os.ModePerm); err != nil {
		return err
	}

	logFile, err := os.OpenFile(filepath.Join("extracts", "peppol_go.log"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
	if err != nil {
		return fmt.Errorf("failed to open log file: %w", err)
	}
	defer logFile.Close()
	log.SetOutput(logFile)

	startTime := time.Now()
	log.Printf("INFO: Starting PEPPOL sync process")

	if cleanupBefore {
		cleanupExtracts()
	}

	// Download the XML file
	downloadStartTime := time.Now()
	xmlFile, err := downloadXML()
	if err != nil {
		log.Printf("ERROR: Failed to download XML file: %v", err)
		return err
	}
	downloadDuration := time.Since(downloadStartTime)
	fileInfo, _ := os.Stat(xmlFile)
	log.Printf("INFO: Downloaded %d bytes in %s", fileInfo.Size(), downloadDuration)

	// Process the XML file
	processStartTime := time.Now()
	stats, err := processXML(xmlFile)
	if err != nil {
		log.Printf("ERROR: Failed to process XML file: %v", err)
		return err
	}
	processDuration := time.Since(processStartTime)
	totalCards := 0
	for _, count := range stats.CardsByCountry {
		totalCards += count
	}
	throughput := float64(totalCards) / processDuration.Seconds()
	log.Printf("INFO: Processed %d business cards in %s (%.2f cards/sec)", totalCards, processDuration, throughput)

	// Generate report
	if err := generateReport(stats); err != nil {
		log.Printf("ERROR: Failed to generate report: %v", err)
		return err
	}

	if cleanupAfter {
		cleanupTemp()
	}

	totalDuration := time.Since(startTime)
	log.Printf("INFO: PEPPOL sync process finished in %s", totalDuration)

	return nil
}

type Stats struct {
	CardsByCountry map[string]int
}

func processXML(inputFile string) (*Stats, error) {
	if verbose && !silent {
		fmt.Printf("Processing XML file: %s\n", inputFile)
	}

	xmlFile, err := os.Open(inputFile)
	if err != nil {
		return nil, err
	}
	defer xmlFile.Close()

	decoder := xml.NewDecoder(xmlFile)

	var rootElement xml.StartElement
	// Find the root element and its attributes
	for {
		token, err := decoder.Token()
		if err != nil {
			if err == io.EOF {
				return nil, fmt.Errorf("XML file is empty or contains no elements")
			}
			return nil, err
		}
		if se, ok := token.(xml.StartElement); ok {
			rootElement = se.Copy()
			break
		}
	}

	fileHandles := make(map[string]*os.File)
	fileSequences := make(map[string]int)
	fileSizes := make(map[string]int64)
	stats := &Stats{
		CardsByCountry: make(map[string]int),
	}

	for {
		token, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		if se, ok := token.(xml.StartElement); ok && se.Name.Local == "businesscard" {
			var bc BusinessCardRaw
			if err := decoder.DecodeElement(&bc, &se); err != nil {
				return nil, err
			}

			// Find country code from inner XML
			country := "XX"
			subDecoder := xml.NewDecoder(bytes.NewReader(bc.InnerXML))
			for {
				subToken, subErr := subDecoder.Token()
				if subErr != nil {
					break
				}
				if sse, ok := subToken.(xml.StartElement); ok && sse.Name.Local == "entity" {
					for _, attr := range sse.Attr {
						if attr.Name.Local == "countrycode" {
							country = strings.ToUpper(attr.Value)
							break
						}
					}
					break
				}
			}
			if country == "" {
				country = "XX"
			}
			stats.CardsByCountry[country]++

			// Get or create file handle
			f, ok := fileHandles[country]
			if !ok {
				fileSequences[country] = 1
				f, err = getOutputFile(country, fileSequences, fileSizes, fileHandles, rootElement)
				if err != nil {
					return nil, err
				}
			}

			// Check if we need to roll over
			if fileSizes[country] > int64(maxBytes) {
				fileSequences[country]++
				f, err = getOutputFile(country, fileSequences, fileSizes, fileHandles, rootElement)
				if err != nil {
					return nil, err
				}
			}

			// Write business card to file verbatim
			var buf bytes.Buffer
			buf.WriteString("<" + se.Name.Local)
			for _, attr := range se.Attr {
				buf.WriteString(fmt.Sprintf(` %s="%s"`, attr.Name.Local, html.EscapeString(attr.Value)))
			}
			buf.WriteString(">")
			buf.Write(bc.InnerXML)
			buf.WriteString("</" + se.Name.Local + ">\n")

			n, err := f.Write(buf.Bytes())
			if err != nil {
				return nil, err
			}
			fileSizes[country] += int64(n)
		}
	}

	// Close all file handles
	for _, f := range fileHandles {
		f.WriteString(fmt.Sprintf("\n</%s>", rootElement.Name.Local))
		f.Close()
	}

	return stats, nil
}

func generateReport(stats *Stats) error {
	if verbose && !silent {
		fmt.Println("Generating report...")
	}
	reportFile, err := os.Create(filepath.Join("extracts", "report.md"))
	if err != nil {
		return err
	}
	defer reportFile.Close()

	reportFile.WriteString("# PEPPOL Sync Report\n\n")
	reportFile.WriteString(fmt.Sprintf("Generated on: %s\n\n", time.Now().Format("2006-01-02 15:04:05")))
	reportFile.WriteString("| Country | Files | Cards | Size (MB) |\n")
	reportFile.WriteString("|---|---:|---:|---:|\n")

	type reportData struct {
		Files int
		Cards int
		Size  int64
	}

	report := make(map[string]*reportData)

	filepath.Walk("extracts", func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && filepath.Ext(path) == ".xml" {
			country := filepath.Base(filepath.Dir(path))
			if _, ok := report[country]; !ok {
				report[country] = &reportData{}
			}
			report[country].Files++
			report[country].Size += info.Size()
		}
		return nil
	})

	var totalFiles int
	var totalCards int
	var totalSize int64

	for country, data := range report {
		data.Cards = stats.CardsByCountry[country]
		reportFile.WriteString(fmt.Sprintf("| %s | %d | %d | %.2f |\n", country, data.Files, data.Cards, float64(data.Size)/(1024*1024)))
		totalFiles += data.Files
		totalCards += data.Cards
		totalSize += data.Size
	}

	reportFile.WriteString(fmt.Sprintf("| **Total** | **%d** | **%d** | **%.2f** |\n", totalFiles, totalCards, float64(totalSize)/(1024*1024)))

	return nil
}

func getOutputFile(country string, sequences map[string]int, sizes map[string]int64, handles map[string]*os.File, rootElement xml.StartElement) (*os.File, error) {
	// Close existing file if open
	if f, ok := handles[country]; ok {
		f.WriteString(fmt.Sprintf("\n</%s>", rootElement.Name.Local))
		f.Close()
	}

	outputPath := filepath.Join("extracts", country)
	if err := os.MkdirAll(outputPath, os.ModePerm); err != nil {
		return nil, err
	}

	fileName := filepath.Join(outputPath, fmt.Sprintf("business-cards.%06d.xml", sequences[country]))
	f, err := os.Create(fileName)
	if err != nil {
		return nil, err
	}

	f.WriteString("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")

	var rootTag bytes.Buffer
	rootTag.WriteString("<" + rootElement.Name.Local)
	for _, attr := range rootElement.Attr {
		rootTag.WriteString(fmt.Sprintf(` %s="%s"`, attr.Name.Local, html.EscapeString(attr.Value)))
	}
	rootTag.WriteString(">")
	f.WriteString(rootTag.String())

	handles[country] = f
	sizes[country] = 0

	return f, nil
}

func cleanupExtracts() {
	if verbose && !silent {
		fmt.Println("Cleaning up extracts directory...")
	}
	filepath.Walk("extracts", func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() && filepath.Ext(path) == ".xml" {
			os.Remove(path)
		}
		return nil
	})
}

func cleanupTemp() {
	if verbose && !silent {
		fmt.Println("Cleaning up temp directory...")
	}
	os.RemoveAll(tempDir)
}

// ... (downloadXML and progressReader remain the same) ...
func downloadXML() (string, error) {
	url := "https://directory.peppol.eu/export/businesscards"
	outputFile := filepath.Join(tempDir, "directory-export-business-cards.xml")

	if !force {
		if _, err := os.Stat(outputFile); err == nil {
			if verbose && !silent {
				fmt.Printf("Using existing file: %s\n", outputFile)
			}
			return outputFile, nil
		}
	}

	if verbose && !silent {
		fmt.Printf("Downloading PEPPOL export from %s\n", url)
	}

	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("bad status: %s", resp.Status)
	}

	out, err := os.Create(outputFile)
	if err != nil {
		return "", err
	}
	defer out.Close()

	// Create a progress reader
	pr := &progressReader{
		Reader: resp.Body,
		Total:  resp.ContentLength,
	}

	// Display progress in a separate goroutine
	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				if !silent {
					pr.printProgress()
				}
			case <-pr.done:
				if !silent {
					pr.printProgress()
					fmt.Println()
				}
				return
			}
		}
	}()

	_, err = io.Copy(out, pr)
	close(pr.done) // Signal that the download is complete
	if err != nil {
		return "", err
	}

	return outputFile, nil
}

// progressReader is a wrapper around an io.Reader that allows for progress tracking.
type progressReader struct {
	Reader    io.Reader
	readBytes int64
	Total     int64
	done      chan struct{}
}

func (pr *progressReader) Read(p []byte) (int, error) {
	if pr.done == nil {
		pr.done = make(chan struct{})
	}
	n, err := pr.Reader.Read(p)
	if err == nil {
		pr.readBytes += int64(n)
	}
	return n, err
}

func (pr *progressReader) printProgress() {
	fmt.Printf("\rDownloading... %.2f MB", float64(pr.readBytes)/(1024*1024))
}