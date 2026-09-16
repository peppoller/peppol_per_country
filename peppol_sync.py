#!/usr/bin/env python3
"""
PEPPOL Business Cards Synchronization Script
Streams through large XML export and splits by country
"""
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict, OrderedDict
import re
try:
    from lxml import etree as ET
except ImportError:
    sys.exit("lxml is not installed. Please run 'pip install lxml' to use this script.")
from typing import BinaryIO, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import time
import zlib
import subprocess
import socket
import getpass
try:
    import resource
except ImportError:  # not available on Windows
    resource = None


def convert_card(card_xml: str):
    """Parse one <businesscard> and return (country, regdate, entity name, pretty bytes, error).
    Module-level so worker processes can run it."""
    try:
        root = ET.fromstring(card_xml.encode('utf-8'))
    except ET.XMLSyntaxError as e:
        return None, None, None, None, f"Error parsing card XML: {e} - XML: {card_xml[:200]}"
    entity = root.find(".//entity")
    country = entity.get("countrycode") if entity is not None else None
    regdate = root.find(".//regdate")
    date = None
    if regdate is not None and regdate.text:
        text = regdate.text.strip()
        if len(text) >= 10:
            date = text[:10]
    name = root.find(".//name")
    entity_name = name.get("name") if name is not None else None
    # Pretty print with lxml, indented one level under <root>
    pretty = ET.tostring(root, pretty_print=True, encoding='unicode')
    card_bytes = ("\n    " + pretty.strip().replace('\n', '\n    ')).encode('utf-8')
    return country, date, entity_name, card_bytes, None


def convert_batch(cards):
    return [convert_card(c) for c in cards]


class PeppolSync:
    """Main class for PEPPOL export synchronization"""

    def __init__(self, tmp_dir: str = "tmp", verbose: bool = False, max_bytes: int = 1000000, keep_tmp: bool = False, jobs: int = 1):
        self.tmp_dir = Path(tmp_dir)
        self.verbose = verbose
        self.extracts_dir = Path("extracts")
        self.docs_dir = Path("docs")
        self.log_dir = Path("log")
        self.file_stats = {}
        self.max_bytes = max_bytes
        self.keep_tmp = keep_tmp
        self.jobs = max(1, jobs)
        self.max_open_files = self._open_file_budget()

        # Create directories
        self.tmp_dir.mkdir(exist_ok=True)
        self.extracts_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)

        # Statistics
        self.stats = defaultdict(int)
        self.file_count = 0  # Track number of output files created

        # Setup logging
        log_file = self.log_dir / "peppol_sync.log"
        self.log_handle = open(log_file, "w") # Changed to 'w' to start empty
        self.log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"User: {getpass.getuser()}, Host: {socket.gethostname()}, CWD: {os.getcwd()}")

    @staticmethod
    def _open_file_budget() -> int:
        """How many output files may be open at once (one per country/month bucket).
        Raise the soft limit as far as allowed; keep headroom for other descriptors."""
        budget = 1024
        if resource is not None:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            wanted = min(hard, 65536) if hard != resource.RLIM_INFINITY else 65536
            if soft < wanted:
                try:
                    resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
                    soft = wanted
                except (ValueError, OSError):
                    pass
            budget = max(64, soft - 128)
        return budget

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
            # Open URL connection.
            # urllib sends "Accept-Encoding: identity" by default, which directory.peppol.eu
            # rejects with HTTP 406 since Sept 2026. Advertise gzip instead and decompress
            # on the fly if the server actually compresses the response.
            request = Request(url, headers={
                "User-Agent": "peppol_per_country (https://github.com/peppoller/peppol_per_country)",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
            })
            with urlopen(request) as response:
                # Download in chunks
                chunk_size = 8192  # 8KB chunks
                downloaded = 0
                encoding = (response.headers.get("Content-Encoding") or "").lower()
                decompressor = None
                if encoding == "gzip":
                    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                elif encoding == "deflate":
                    decompressor = zlib.decompressobj()
                self.log(f"download_xml: HTTP {response.status}, Content-Encoding: {encoding or 'none'}")

                with open(output_file, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            if decompressor:
                                f.write(decompressor.flush())
                            break

                        if decompressor:
                            chunk = decompressor.decompress(chunk)
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




    def bucket_file(self, bucket: str, sequence: int) -> Path:
        """Path of the n-th file of a country/month bucket, e.g. extracts/BE/2026-08/business-cards.000003.xml"""
        country, month = bucket.split("/", 1)
        return self.extracts_dir / country / month / f"business-cards.{sequence:06d}.xml"

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

    def iter_cards(self, f, chunk_size: int = 1024 * 1024):
        """Yield (header, None) once, then (None, card_xml) for every <businesscard>.
        Scans a rolling buffer by index; the buffer is only re-sliced when a chunk is appended."""
        separator = "</businesscard>"
        buffer = ""
        while "<businesscard>" not in buffer:
            chunk = f.read(chunk_size)
            if not chunk:
                return
            buffer += chunk
        header_end = buffer.find("<businesscard>")
        yield buffer[:header_end], None
        pos = header_end
        while True:
            sep_index = buffer.find(separator, pos)
            if sep_index < 0:
                chunk = f.read(chunk_size)
                if not chunk:
                    return
                buffer = buffer[pos:] + chunk
                pos = 0
                continue
            end_index = sep_index + len(separator)
            yield None, buffer[pos:end_index]
            pos = end_index

    def iter_converted(self, cards):
        """Yield convert_card() results in input order, using a worker pool when jobs > 1.
        Prefetch is bounded so the input file is never read far ahead of the writer."""
        if self.jobs <= 1:
            for card_xml in cards:
                yield convert_card(card_xml)
            return

        import multiprocessing as mp
        from collections import deque
        try:
            ctx = mp.get_context("fork")
        except ValueError:
            ctx = mp.get_context()
        batch_size = 2000
        max_pending = self.jobs * 4
        pending = deque()
        with ctx.Pool(self.jobs) as pool:
            batch = []
            for card_xml in cards:
                batch.append(card_xml)
                if len(batch) >= batch_size:
                    pending.append(pool.apply_async(convert_batch, (batch,)))
                    batch = []
                    if len(pending) >= max_pending:
                        yield from pending.popleft().get()
            if batch:
                pending.append(pool.apply_async(convert_batch, (batch,)))
            while pending:
                yield from pending.popleft().get()

    def process_xml(self, input_file: Path):
        """Process XML file using text splitting for performance"""
        self.announce(f"Processing {input_file.name} with text splitting ({self.jobs} worker(s))")
        self.log(f"Starting text processing: {input_file} with {self.jobs} worker(s)")

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        start_time = time.time()  # Record start time

        open_files: "OrderedDict[str, BinaryIO]" = OrderedDict()  # bucket -> handle, LRU order
        processed_cards = 0
        footer = b"\n</root>\n"        # closes a file that is rotated
        final_footer = b"\n</root>"    # closes the last file of a bucket (no trailing newline, as before)

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                items = self.iter_cards(f)
                try:
                    header, _ = next(items)
                except StopIteration:
                    self.log("No <businesscard> tag found.")
                    return 0

                # Remove creationdt from header to make it static
                header = re.sub(r'creationdt="[^"]*"', '', header)
                header_bytes = header.replace('><', '>\n<').encode('utf-8')

                cards = (card_xml for _, card_xml in items)
                for country, date, entity_name, card_bytes, error in self.iter_converted(cards):
                    processed_cards += 1
                    if processed_cards % 100000 == 0:
                        duration = time.time() - start_time
                        throughput = processed_cards / duration if duration > 0 else 0
                        self.progress(
                            f"{processed_cards:,} business cards in {duration:.1f}s: {throughput:.0f} cards/sec")

                    if error:
                        self.log(error)
                        continue
                    if not country:
                        self.log(f"Could not extract country from card: {card_bytes[:100]!r}")
                        continue

                    self.stats[f"country_{country}"] += 1

                    # Bucket by registration month; cards without regdate go to 0000-00
                    month = date[:7] if date else "0000-00"

                    if not date:
                        safe_name = "".join(filter(str.isalnum, entity_name or ""))[:5].upper()
                        date = f"2000-{safe_name}" if safe_name else "2000-UNKNOWN"

                    self.stats[f"date_{date}"] += 1

                    # File writing logic: one sequence of size-limited files per country/month
                    bucket = f"{country}/{month}"
                    stats = self.file_stats.setdefault(bucket, {'sequence': 1})
                    handle = open_files.get(bucket)

                    if handle is not None:
                        open_files.move_to_end(bucket)
                        if stats['size'] > self.max_bytes:
                            handle.write(footer)
                            handle.close()
                            del open_files[bucket]
                            stats['sequence'] += 1
                            handle = None

                    if handle is None:
                        if len(open_files) >= self.max_open_files:
                            # Evict least recently used handle; the file is reopened in
                            # append mode if needed and gets its footer in finalize.
                            _, victim = open_files.popitem(last=False)
                            victim.close()
                        output_path = self.bucket_file(bucket, stats['sequence'])
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        # Binary mode with our own byte counter: tell() on a text-mode
                        # file is expensive and was called once per card.
                        handle = open(output_path, "ab")
                        stats['size'] = handle.tell()
                        if stats['size'] == 0:
                            handle.write(header_bytes)
                            stats['size'] = len(header_bytes)
                            self.file_count += 1
                        open_files[bucket] = handle

                    handle.write(card_bytes)
                    stats['size'] += len(card_bytes)
        finally:
            # Close every current file with a footer: the ones still open directly,
            # the ones evicted from the cache by reopening them in append mode.
            for bucket, handle in open_files.items():
                handle.write(final_footer)
                handle.close()
            for bucket, stats in self.file_stats.items():
                if bucket in open_files:
                    continue
                path = self.bucket_file(bucket, stats['sequence'])
                if path.exists():
                    with open(path, "ab") as handle:
                        handle.write(final_footer)
            open_files.clear()

        duration = time.time() - start_time
        throughput = processed_cards / duration if duration > 0 else 0
        self.success(f"Processed {processed_cards:,} business cards in {duration:.0f}s: {throughput:.0f} cards/sec")
        self.log(f"Processed {processed_cards:,} business cards in {duration:.0f}s: {throughput:.0f} cards/sec")

        return processed_cards

    def generate_report(self):
        """Generate a markdown report of the sync operation"""
        report_path = self.docs_dir / "report.md"
        self.announce(f"Generating report: {report_path}")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# PEPPOL Sync Report\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("| Country | Months | Files | Cards | Size (MB) |\n")
            f.write("|---|---:|---:|---:|---:|\n")

            total_months = 0
            total_files = 0
            total_cards = 0
            total_size_mb = 0

            countries = sorted([k.replace("country_", "") for k in self.stats.keys() if k.startswith("country_")])

            for country in countries:
                country_dir = self.extracts_dir / country
                if not country_dir.is_dir():
                    continue

                files = list(country_dir.glob("**/*.xml"))
                month_count = len({p.parent for p in files})
                file_count = len(files)
                card_count = self.stats.get(f"country_{country}", 0)
                size_bytes = sum(p.stat().st_size for p in files)
                size_mb = size_bytes / (1024 * 1024)

                f.write(f"| {country} | {month_count} | {file_count} | {card_count} | {size_mb:.2f} |\n")

                total_months += month_count
                total_files += file_count
                total_cards += card_count
                total_size_mb += size_mb

            f.write(f"| **Total** | **{total_months}** | **{total_files}** | **{total_cards}** | **{total_size_mb:.2f}** |\n")

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
        # Remove directories left empty (deepest first)
        for dir_path in sorted(self.extracts_dir.glob("**/"), key=lambda p: len(p.parts), reverse=True):
            if dir_path != self.extracts_dir and dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()
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
        help="Maximum number of bytes per output file (default: 2000000)"
    )

    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="Worker processes for XML parsing (default: CPU count - 1; 1 = no worker pool)"
    )

    args = parser.parse_args()

    # Create sync instance
    syncer = PeppolSync(
        tmp_dir=args.tmp,
        verbose=args.verbose,
        max_bytes=args.max,
        keep_tmp=args.keep_tmp,
        jobs=args.jobs
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
