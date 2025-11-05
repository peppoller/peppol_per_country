#!/usr/bin/env python3
"""
PEPPOL Business Cards Synchronization Script
Streams through large XML export and splits by country/month
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
try:
    from lxml import etree as ET
except ImportError:
    sys.exit("lxml is not installed. Please run 'pip install lxml' to use this script.")
from typing import Dict, TextIO, Optional
from urllib.request import urlopen
from urllib.error import URLError
import time
import subprocess
import socket
import getpass


class PeppolSync:
    """Main class for PEPPOL export synchronization"""

    def __init__(self, tmp_dir: str = "tmp", verbose: bool = False, max_bytes: int = 1000000, keep_tmp: bool = False):
        self.tmp_dir = Path(tmp_dir)
        self.verbose = verbose
        self.extracts_dir = Path("extracts")
        self.file_stats = {}
        self.max_bytes = max_bytes
        self.keep_tmp = keep_tmp

        # Create directories
        self.tmp_dir.mkdir(exist_ok=True)
        self.extracts_dir.mkdir(exist_ok=True)

        # Statistics
        self.stats = defaultdict(int)
        self.file_count = 0  # Track number of output files created

        # Setup logging
        log_file = self.extracts_dir / "peppol_sync.log"
        self.log_handle = open(log_file, "w") # Changed to 'w' to start empty
        self.log(f"User: {getpass.getuser()}, Host: {socket.gethostname()}, CWD: {os.getcwd()}")

    def log(self, message: str):
        """Write to log file"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_handle.write(f"{timestamp} | {message}\n")
        self.log_handle.flush()

    def progress(self, message: str):
        """Print progress message"""
        if not self.verbose:
            print(f"\r... {message}", end="", flush=True)
        else:
            print(f"... {message}")

    def success(self, message: str):
        """Print success message"""
        print(f"\n✅  {message}")

    def announce(self, message: str):
        """Print announcement"""
        print(f"⏳  {message}")

    def download_xml(self, force: bool = False) -> Path:
        """Download PEPPOL XML export if needed"""
        url = "https://directory.peppol.eu/export/businesscards"
        output_file = self.tmp_dir / "directory-export-business-cards.xml"

        # Skip if file exists and not forcing
        if output_file.exists() and not force:
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            self.log(f"Using existing file: {output_file} ({file_size_mb:.1f} MB)")
            return output_file

        self.announce(f"Downloading PEPPOL export from {url}")
        self.log(f"download_xml: {url}")

        start_time = time.time() # Record start time

        try:
            # Open URL connection
            with urlopen(url) as response:
                # Download in chunks
                chunk_size = 8192  # 8KB chunks
                downloaded = 0

                with open(output_file, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress every MB
                        if downloaded % (100 * 1024 * 1024) == 0 or not chunk:
                            duration = time.time() - start_time
                            downloaded_mb = downloaded / (1024 * 1024)
                            throughput = downloaded_mb / duration if duration > 0 else 0
                            self.progress(f"Downloading {downloaded_mb:.1f} MB @ {duration:.1f}s: {throughput:.2f} MB/s")

            end_time = time.time() # Record end time

            # Verify file was created
            if output_file.exists():
                file_size_mb = output_file.stat().st_size / (1024 * 1024)
                duration = end_time - start_time
                throughput = file_size_mb / duration if duration > 0 else 0
                self.success(f"Downloaded to {output_file.name} ({file_size_mb:.0f} MB) in {duration:.0f}s at {throughput:.0f} MB/s")
                self.log(f"download_xml: {file_size_mb:.0f} MB downloaded in {duration:.0f}s at {throughput:.0f} MB/s")
                return output_file
            else:
                raise FileNotFoundError(f"Download completed but file not found: {output_file}")

        except URLError as e:
            error_msg = f"Failed to download from {url}: {e}"
            self.log(f"download_xml error: {error_msg}")
            raise Exception(error_msg)




    def extract_country_from_etree(self, element: ET.Element) -> Optional[str]:
        """Extract country code from ElementTree element"""
        entity = element.find(".//entity")
        if entity is not None:
            return entity.get("countrycode")
        return None

    def extract_date_from_etree(self, element: ET.Element) -> Optional[str]:
        """Extract registration date from ElementTree element"""
        regdate = element.find(".//regdate")
        if regdate is not None and regdate.text:
            date_str = regdate.text.strip()
            if len(date_str) >= 10:
                return date_str[:10]
        return None

    def extract_entity_name_from_etree(self, element: ET.Element) -> Optional[str]:
        """Extract entity name from ElementTree element"""
        name = element.find(".//name")
        if name is not None:
            return name.get("name")
        return None

    def process_xml(self, input_file: Path):
        """Process XML file using text splitting for performance"""
        self.announce(f"Processing {input_file.name} with text splitting")
        self.log(f"Starting text processing: {input_file}")

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        start_time = time.time()  # Record start time

        chunk_size = 1024 * 1024  # 1MB
        buffer = ""
        separator = "</businesscard>"

        header = ""
        header_found = False
        open_files: Dict[str, TextIO] = {}
        processed_cards = 0

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                # 1. Find header
                while not header_found:
                    chunk = f.read(chunk_size)
                    if not chunk: break
                    buffer += chunk
                    if "<businesscard>" in buffer:
                        header_end = buffer.find("<businesscard>")
                        header = buffer[:header_end]
                        buffer = buffer[header_end:]
                        header_found = True

                if not header_found:
                    self.log("No <businesscard> tag found.")
                    return 0

                # 2. Process business cards
                while True:
                    if separator not in buffer:
                        chunk = f.read(chunk_size)
                        if not chunk: break
                        buffer += chunk

                    if separator not in buffer: break

                    end_index = buffer.find(separator) + len(separator)
                    card_xml = buffer[:end_index]
                    buffer = buffer[end_index:]

                    processed_cards += 1
                    if processed_cards % 100000 == 0:
                        duration = time.time() - start_time
                        throughput = processed_cards / duration if duration > 0 else 0
                        self.progress(
                            f"{processed_cards:,} business cards in {duration:.1f}s: {throughput:.0f} cards/sec")

                    try:
                        # Use lxml for fast parsing and pretty printing
                        root = ET.fromstring(card_xml.encode('utf-8'))
                        country = self.extract_country_from_etree(root)
                        date = self.extract_date_from_etree(root)

                        if not country:
                            self.log(f"Could not extract country from card: {card_xml[:100]}")
                            continue

                        self.stats[f"country_{country}"] += 1

                        if not date:
                            entity_name = self.extract_entity_name_from_etree(root)
                            safe_name = "".join(filter(str.isalnum, entity_name or ""))[:5].upper()
                            date = f"2000-{safe_name}" if safe_name else "2000-UNKNOWN"

                        self.stats[f"date_{date}"] += 1

                        # File writing logic
                        stats = self.file_stats.setdefault(country, {'sequence': 1})
                        output_path = self.extracts_dir / country / f"business-cards.{stats['sequence']:06d}.xml"

                        if country in open_files and open_files[country].tell() > self.max_bytes:
                            open_files[country].write('\n</root>\n')
                            open_files[country].close()
                            del open_files[country]
                            stats['sequence'] += 1
                            output_path = self.extracts_dir / country / f"business-cards.{stats['sequence']:06d}.xml"

                        if country not in open_files:
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            file_handle = open(output_path, "a", encoding="utf-8")
                            if file_handle.tell() == 0:
                                file_handle.write(header.replace('><', '>\n<'))
                                self.file_count += 1
                            open_files[country] = file_handle

                        # Pretty print the XML using lxml
                        pretty_card_xml = ET.tostring(root, pretty_print=True, encoding='unicode')
                        indented_card = "    " + pretty_card_xml.strip().replace('\n', '\n    ')
                        open_files[country].write("\n" + indented_card)

                    except ET.XMLSyntaxError as e:
                        self.log(f"Error parsing card XML: {e} - XML: {card_xml[:200]}")
                        continue
        finally:
            for handle in open_files.values():
                handle.write("\n</root>")
                handle.close()

        duration = time.time() - start_time
        throughput = processed_cards / duration if duration > 0 else 0
        self.success(f"Processed {processed_cards:,} business cards in {duration:.0f}s: {throughput:.0f} cards/sec")
        self.log(f"Processed {processed_cards:,} business cards in {duration:.0f}s: {throughput:.0f} cards/sec")

        countries = [k.replace("country_", "") for k in self.stats.keys() if k.startswith("country_")]

        return processed_cards

    def generate_report(self):
        """Generate a markdown report of the sync operation"""
        self.announce("Generating report")
        report_path = self.extracts_dir / "report.md"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# PEPPOL Sync Report\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("| Country | Files | Cards | Size (MB) |\n")
            f.write("|---|---:|---:|---:|\n")

            total_files = 0
            total_cards = 0
            total_size_mb = 0

            countries = sorted([k.replace("country_", "") for k in self.stats.keys() if k.startswith("country_")])

            for country in countries:
                country_dir = self.extracts_dir / country
                if not country_dir.is_dir():
                    continue

                files = list(country_dir.glob("*.xml"))
                file_count = len(files)
                card_count = self.stats.get(f"country_{country}", 0)
                size_bytes = sum(p.stat().st_size for p in files)
                size_mb = size_bytes / (1024 * 1024)

                f.write(f"| {country} | {file_count} | {card_count} | {size_mb:.2f} |\n")

                total_files += file_count
                total_cards += card_count
                total_size_mb += size_mb

            f.write(f"| **Total** | **{total_files}** | **{total_cards}** | **{total_size_mb:.2f}** |\n")

        self.success(f"Report generated at {report_path}")
        self.log(f"Report generated at {report_path}")

    def cleanup_extracts(self):
        """Delete all existing XML files in the extracts directory"""
        self.announce("Cleaning up existing extracts")
        deleted_files = 0
        for file_path in self.extracts_dir.glob("**/*.xml"):
            if file_path.is_file():
                file_path.unlink()
                deleted_files += 1
        self.success(f"Deleted {deleted_files} XML files from {self.extracts_dir}/")
        self.log(f"Deleted {deleted_files} XML files from {self.extracts_dir}/")

    def sync(self, force_download: bool = False, cleanup: bool = False):
        """Main sync operation"""
        self.log("Starting sync operation")

        if cleanup:
            self.cleanup_extracts()

        self.announce(f"Max bytes per file: {self.max_bytes:,}")

        # Download XML file if needed
        try:
            input_file = self.download_xml(force=force_download)
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return 1

        # Show file size
        file_size_mb = input_file.stat().st_size / (1024 * 1024)
        self.announce(f"Processing file: {input_file.name} ({file_size_mb:.1f} MB)")

        # Process XML
        try:
            cards_processed = self.process_xml(input_file)

            # Show summary
            print("\n📊 Summary:")
            print(f"   Total business cards: {cards_processed:,}")
            
            countries = [k.replace("country_", "") for k in self.stats.keys() if k.startswith("country_")]
            print(f"   Countries found: {len(countries)}")
            self.log(f"Countries found: {len(countries)}")

            print(f"   Output files created: {self.file_count}")
            self.log(f"Output files created: {self.file_count}")
            print(f"   Output directory: {self.extracts_dir}/")

            self.success("Sync complete!")
            self.generate_report()
            return 0

        except Exception as e:
            print(f"\n❌ Error: {e}")
            self.log(f"Error: {e}")
            return 1

        finally:
            self.log_handle.close()

    def cleanup_after(self):
        """Close any open resources and clean up temp files"""
        # Close log file
        if self.log_handle and not self.log_handle.closed:
            self.log_handle.close()

        # Clean up tmp files unless keep_tmp is set
        if not self.keep_tmp and self.tmp_dir.exists():
            import shutil
            try:
                files_removed = 0
                for file_path in self.tmp_dir.glob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                        files_removed += 1

                if files_removed > 0:
                    print(f"\n🧹 Cleaned up {files_removed} temporary file(s) from {self.tmp_dir}/")
            except Exception as e:
                print(f"\n⚠️  Warning: Could not clean up tmp files: {e}")

    def show_huge_files(self, number: int = 10) -> int:
        """Show the N largest XML files under extracts/"""
        self.announce(f"Finding the {number} largest XML files under {self.extracts_dir}/")
        command = f"find {self.extracts_dir} -name \"*.xml\" -type f -exec du -h {{}} + | sort -rh | head -n {number}"
        
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
            print(result.stdout)
            self.success(f"Displayed {number} largest files.")
            return 0
        except subprocess.CalledProcessError as e:
            print(f"❌ Error executing command: {e}")
            print(f"Stderr: {e.stderr}")
            self.log(f"Error in show_huge_files: {e.stderr}")
            return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Synchronize PEPPOL export into git-managed files",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "action",
        choices=["sync", "check", "download", "huge"],
        help="Action to perform"
    )

    parser.add_argument(
        "-V", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "-F", "--force",
        action="store_true",
        help="Force re-download of XML file even if it exists"
    )

    parser.add_argument(
        "-C", "--nocleanup",
        action="store_true",
        help="Do not delete existing XML files in extracts/ before starting (default: delete)"
    )

    parser.add_argument(
        "-K" ,"--keep-tmp",
        action="store_true",
        help="Keep temporary files after processing (default: delete)"
    )

    parser.add_argument(
        "-T", "--tmp",
        default="tmp",
        help="Temporary directory (default: tmp)"
    )

    parser.add_argument(
        "-M", "--max",
        type=int,
        default=2000000,
        help="Maximum number of bytes per output file (default: 1000000)"
    )

    args = parser.parse_args()

    # Create sync instance
    syncer = PeppolSync(
        tmp_dir=args.tmp,
        verbose=args.verbose,
        max_bytes=args.max,
        keep_tmp=args.keep_tmp
    )

    try:
        if args.action == "sync":
            return syncer.sync(force_download=args.force, cleanup=not args.nocleanup)
        elif args.action == "download":
            try:
                input_file = syncer.download_xml(force=args.force)
                file_size_mb = input_file.stat().st_size / (1024 * 1024)
                print(f"\n📁 Downloaded file:")
                print(f"   Location: {input_file}")
                print(f"   Size: {file_size_mb:.1f} MB")
                return 0
            except Exception as e:
                print(f"\n❌ Download failed: {e}")
                return 1
        elif args.action == "check":
            print("✅ Configuration OK")
            print(f"   Temp directory: {syncer.tmp_dir}")
            print(f"   Extracts directory: {syncer.extracts_dir}")
            return 0
        elif args.action == "huge":
            return syncer.show_huge_files(10)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1
    finally:
        syncer.cleanup_after()


if __name__ == "__main__":
    sys.exit(main())
