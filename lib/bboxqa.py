#!/usr/bin/env python3

"""
This module provides functionality to assess whether text lines in page JSON data
are within the boundaries of their corresponding page images. It includes utilities
to fetch page data from S3, retrieve image dimensions from IIIF URIs, and validate
line coordinates.
"""

import argparse
import json
import logging
import re
import sys
import time
from typing import List, Optional, Iterator, Dict, Any
import xml.etree.ElementTree as ET

import requests
import urllib3
from dotenv import load_dotenv
from smart_open import open as smart_open  # type: ignore[import]

from page_statistics import PageStatisticsProcessor
from impresso_cookbook import (  # type: ignore[import]
    get_s3_client,
    parse_s3_path,
    setup_logging,
    get_transport_params,
    get_timestamp,
)

urllib3.disable_warnings()
load_dotenv()

log = logging.getLogger(__name__)

# Global cache for Gallica pagination XML to avoid repeated requests for the same issue
_gallica_xml_cache: Dict[str, ET.Element] = {}


def fetch_all_pages(s3_prefix: str, random: bool = False) -> Iterator[Dict[str, Any]]:
    """
    Fetch all pages from all .jsonl.bz2 files located under the given S3 prefix.

    Args:
        s3_prefix (str): The S3 or local prefix to search for .jsonl.bz2 files.
        random (bool): If True, the order of the pages returned is randomized.

    Returns:
        iter: A generator that yields page JSON objects from all matching files.
    """
    transport_params = (
        {"client": get_s3_client()} if s3_prefix.startswith("s3://") else {}
    )
    s3_client = get_s3_client()
    bucket, prefix = parse_s3_path(s3_prefix)

    # List all files under the prefix
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [
        obj["Key"]
        for obj in response.get("Contents", [])
        if obj["Key"].endswith("pages.jsonl.bz2")
    ]

    if random:
        import random as rnd

        rnd.shuffle(objects)

    for obj_key in objects:
        file_path = f"s3://{bucket}/{obj_key}"
        with smart_open(
            file_path, "rb", encoding="utf-8", transport_params=transport_params
        ) as f:
            for line in f:
                yield json.loads(line)


def fetch_image_dimensions_from_gallica_xml(
    ark_id: str, page_number: str
) -> tuple[int | None, int | None]:
    """
    Fetch image dimensions from Gallica's pagination XML service.

    Args:
        ark_id (str): The ARK identifier (e.g., 'bpt6k6703122r')
        page_number (str): The page number (e.g., 'f4' -> '4')

    Returns:
        tuple[int | None, int | None]: A tuple containing the width and height
    """
    global _gallica_xml_cache

    try:
        # Extract numeric page number from format like 'f4'
        if page_number.startswith("f"):
            page_num = page_number[1:]
        else:
            page_num = page_number

        # Check if we already have the XML cached for this ARK ID
        if ark_id in _gallica_xml_cache:
            root = _gallica_xml_cache[ark_id]
            log.debug(f"Using cached pagination XML for ARK {ark_id}")
        else:
            # Fetch and cache the XML
            pagination_url = f"https://gallica.bnf.fr/services/Pagination?ark={ark_id}"
            log.info(f"Fetching pagination XML from {pagination_url}")
            response = requests.get(pagination_url, verify=False, timeout=10)
            response.raise_for_status()

            # Parse XML and cache it
            root = ET.fromstring(response.content)
            _gallica_xml_cache[ark_id] = root
            log.info(f"Cached pagination XML for ARK {ark_id}")

        # Find the page with the matching order number
        for page in root.findall(".//page"):
            ordre = page.find("ordre")
            if ordre is not None and ordre.text == page_num:
                width_elem = page.find("image_width")
                height_elem = page.find("image_height")

                if (
                    width_elem is not None
                    and height_elem is not None
                    and width_elem.text
                    and height_elem.text
                ):
                    width = int(width_elem.text)
                    height = int(height_elem.text)
                    log.debug(f"Found dimensions for page {page_num}: {width}x{height}")
                    return width, height

        log.warning(f"Page {page_num} not found in pagination XML for {ark_id}")
        return None, None

    except Exception as e:
        log.error(
            f"Failed to fetch dimensions from Gallica XML for {ark_id}, page"
            f" {page_number}: {e}"
        )
        return None, None


def fetch_image_dimensions(iiif_base_uri: str) -> tuple[int | None, int | None]:
    """
    Fetch the dimensions (width and height) of an image from its IIIF base URI.
    For Gallica URIs, uses the pagination XML service for efficiency.

    Args:
        iiif_base_uri (str): The IIIF base URI of the image.

    Returns:
        tuple[int | None, int | None]: A tuple containing the width and height of the
        image in pixels.

    Raises:
        Exception: If the dimensions cannot be fetched after multiple attempts.
    """
    # Check if this is a Gallica IIIF URI and extract ARK ID and page
    gallica_pattern = r"https://gallica\.bnf\.fr/iiif/ark:/12148/([^/]+)/(f\d+)"
    gallica_match = re.match(gallica_pattern, iiif_base_uri)

    if gallica_match:
        ark_id = gallica_match.group(1)
        page_number = gallica_match.group(2)
        log.debug(
            f"Detected Gallica URI, using pagination XML for ARK {ark_id}, page"
            f" {page_number}"
        )
        return fetch_image_dimensions_from_gallica_xml(ark_id, page_number)

    # Fallback to original IIIF info.json method for non-Gallica URIs
    iiif_manifest = f"{iiif_base_uri}/info.json"
    attempts = 4
    for attempt in range(attempts + 1):
        try:
            log.debug(
                "Loading IIIF manifest from %s (attempt %d)", iiif_manifest, attempt + 1
            )
            response = requests.get(
                url=iiif_manifest, verify=False, timeout=1 + attempt
            )
            response.raise_for_status()
            info = response.json()
            log.debug(
                f"Fetched image dimensions from {iiif_manifest}:"
                f" {info['width']}x{info['height']}"
            )
            return info["width"], info["height"]
        except Exception as e:
            log.error(f"Attempt {attempt + 1} failed for {iiif_manifest}: {e}")

            time.sleep(1 + attempt)
            if attempt == attempts:  # On the last attempt, log and exit
                log.error(
                    f"Failed to fetch image dimensions from {iiif_manifest} after 3"
                    " attempts."
                )
                raise e
    return None, None


def check_lines_within_boundaries(
    page_json: dict, image_width: int, image_height: int
) -> dict:
    """
    Validate that all text lines, paragraphs, and regions in the page JSON are within
    the boundaries of the page image.

    Args:
        page_json (dict): The JSON data of the page.
        image_width (int): The width of the page image in pixels.
        image_height (int): The height of the page image in pixels.

    Returns:
        dict: A dictionary containing validation results, including the total number
        of lines and details of out-of-bounds elements.
    """

    out_of_bounds_lines = []
    out_of_bounds_paragraphs = []
    out_of_bounds_regions = []
    total_lines = 0
    current_pOf = None

    for region_seq, region in enumerate(page_json.get("r", [])):
        if "pOf" in region:
            current_pOf = region["pOf"]

        # Check region boundaries
        if "c" in region and len(region["c"]) >= 4:
            x, y, width, height = region["c"]
            if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
                log.error(f"Region out of bounds: {region['c']}")
                out_of_bounds_regions.append(
                    {
                        "region_seq": region_seq,
                        "coord": region["c"],
                        "pOf": current_pOf,
                        "excess_width": max(0, x + width - image_width),
                        "excess_height": max(0, y + height - image_height),
                        "excess_x": max(0, -x),
                        "excess_y": max(0, -y),
                    }
                )

        for paragraph_seq, paragraph in enumerate(region.get("p", [])):
            # Check paragraph boundaries
            if "c" in paragraph and len(paragraph["c"]) >= 4:
                x, y, width, height = paragraph["c"]
                if (
                    x < 0
                    or y < 0
                    or x + width > image_width
                    or y + height > image_height
                ):
                    log.error(f"Paragraph out of bounds: {paragraph['c']}")
                    out_of_bounds_paragraphs.append(
                        {
                            "paragraph_seq": paragraph_seq,
                            "coord": paragraph["c"],
                            "pOf": current_pOf,
                            "excess_width": max(0, x + width - image_width),
                            "excess_height": max(0, y + height - image_height),
                            "excess_x": max(0, -x),
                            "excess_y": max(0, -y),
                        }
                    )

            for line_seq, line in enumerate(paragraph.get("l", [])):
                total_lines += 1
                if "c" in line and len(line["c"]) >= 4:
                    x, y, width, height = line["c"]
                    if (
                        x < 0
                        or y < 0
                        or x + width > image_width
                        or y + height > image_height
                    ):
                        log.error(f"Line out of bounds: {line['c']}")
                        out_of_bounds_lines.append(
                            {
                                "line_seq": line_seq,
                                "coord": line["c"],
                                "pOf": current_pOf,
                                "excess_width": max(0, x + width - image_width),
                                "excess_height": max(0, y + height - image_height),
                                "excess_x": max(0, -x),
                                "excess_y": max(0, -y),
                            }
                        )

    return {
        "total_lines": total_lines,
        "out_of_bounds_lines": out_of_bounds_lines,
        "out_of_bounds_paragraphs": out_of_bounds_paragraphs,
        "out_of_bounds_regions": out_of_bounds_regions,
    }


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        args: Command-line arguments (uses sys.argv if None)

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=(
            "Check if all lines in a page JSONL.BZ2 file are within the page image"
            " boundaries."
        )
    )
    parser.add_argument("s3_path", type=str, help="S3 path to the .jsonl.bz2 file.")
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        default="output.json",
        help="S3 or local path to the output file.",
    )
    parser.add_argument(
        "--git_version",
        type=str,
        required=False,
        help="Git version to include in the output JSON.",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        required=False,
        help="Path to the log file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: %(default)s).",
    )
    parser.add_argument(
        "--iiif-gallica-v3",
        action="store_true",
        help=(
            "Patch Gallica IIIF links to the new server"
            " (https://openapi.bnf.fr/iiif/presentation/v3)."
        ),
    )
    return parser.parse_args(args)


class BoundaryCheckProcessor:
    """
    A processor class that checks if text lines are within page image boundaries.
    """

    def __init__(
        self,
        s3_path: str,
        output: str,
        git_version: Optional[str] = None,
        iiif_gallica_v3: bool = False,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
    ) -> None:
        """
        Initializes the BoundaryCheckProcessor with explicit parameters.

        Args:
            s3_path (str): Path to the input S3 file
            output (str): Path to the output file
            git_version (Optional[str]): Git version to include in output
            iiif_gallica_v3 (bool): Whether to patch Gallica IIIF links
            log_level (str): Logging level (default: "INFO")
            log_file (Optional[str]): Path to log file (default: None)
        """
        self.s3_path = s3_path
        self.output = output
        self.git_version = git_version
        self.iiif_gallica_v3 = iiif_gallica_v3
        self.log_level = log_level
        self.log_file = log_file

        # Configure the module-specific logger
        setup_logging(self.log_level, self.log_file, logger=log)

        # Initialize S3 client and timestamp
        self.s3_client = get_s3_client()
        self.timestamp = get_timestamp()

        # Initialize page statistics processor for computing page stats
        self.page_stats_processor = PageStatisticsProcessor(
            input_file="dummy",  # Not used in this context
            output_file="dummy",  # Not used in this context
            log_level=self.log_level,
            log_file=self.log_file,
        )

    def run(self) -> None:
        """
        Runs the boundary check processor, processing all pages in the input file.
        """
        try:
            log.info("Starting line boundary check...")
            year_out_of_bounds_lines = 0
            year_out_of_bounds_paragraphs = 0
            year_out_of_bounds_regions = 0
            year_total_lines = 0
            year_total_out_of_bounds = 0
            year_total_pages = 0

            summary = []

            for page_json in fetch_all_pages(self.s3_path):
                result = self.process_page(page_json)
                if result:
                    summary.append(result)

                    # Update yearly totals
                    year_total_lines += result["total_lines"]
                    year_out_of_bounds_lines += len(result["out_of_bounds_lines"])
                    year_out_of_bounds_paragraphs += len(
                        result["out_of_bounds_paragraphs"]
                    )
                    year_out_of_bounds_regions += len(result["out_of_bounds_regions"])
                    year_total_pages += 1

            year_total_out_of_bounds = (
                year_out_of_bounds_lines
                + year_out_of_bounds_paragraphs
                + year_out_of_bounds_regions
            )

            # Output results
            if self.output:
                with smart_open(
                    self.output,
                    "w",
                    encoding="utf-8",
                    transport_params=get_transport_params(self.output),
                ) as output_file:
                    for entry in summary:
                        output_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            else:
                for entry in summary:
                    print(json.dumps(entry, ensure_ascii=False))

            log.info(
                "Yearly summary: %d lines, %d out-of-bounds lines, %d out-of-bounds"
                " paragraphs, %d out-of-bounds regions, %d total out-of-bounds, %d"
                " total pages",
                year_total_lines,
                year_out_of_bounds_lines,
                year_out_of_bounds_paragraphs,
                year_out_of_bounds_regions,
                year_total_out_of_bounds,
                year_total_pages,
            )
        except Exception as e:
            log.error(f"Error processing file: {e}", exc_info=True)
            sys.exit(1)

    def process_page(self, page_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Processes a single page JSON object.

        Args:
            page_json (Dict[str, Any]): The page JSON data.

        Returns:
            Optional[Dict[str, Any]]: The processed result or None if processing failed.
        """
        if self.iiif_gallica_v3:
            if "iiif_img_base_uri" in page_json and page_json[
                "iiif_img_base_uri"
            ].startswith("https://gallica.bnf.fr/iiif"):
                page_json["iiif_img_base_uri"] = page_json["iiif_img_base_uri"].replace(
                    "https://gallica.bnf.fr/iiif",
                    "https://openapi.bnf.fr/iiif/presentation/v3",
                )
                log.info(
                    "Patched IIIF link for page %s to %s",
                    page_json["id"],
                    page_json["iiif_img_base_uri"],
                )

        page_id = page_json["id"]
        iiif_base_uri = page_json.get("iiif_img_base_uri", page_json.get("iiif"))
        manifest_info: Dict[str, Any] = {
            "iiif_manifest": {"iiif_base_uri": iiif_base_uri}
        }

        if not iiif_base_uri:
            log.error(f"No IIIF base URI found for page {page_id}.")
            return None

        try:
            image_width, image_height = fetch_image_dimensions(iiif_base_uri)
            log.info("Retrieved IIIF for %s from %s", page_id, iiif_base_uri)
        except Exception as e:
            log.error(f"Failed to fetch image dimensions for {page_id}: {e}")
            image_height = 999999
            image_width = 999999
            manifest_info["error"] = str(e)

        if image_width is None or image_height is None:
            log.error(f"Could not determine image dimensions for {page_id}")
            return None

        validation_results = check_lines_within_boundaries(
            page_json, image_width, image_height
        )

        page_stats = self.page_stats_processor.compute_statistics(page_json)

        entry = {
            "page_id": page_id,
            "ts": self.timestamp,
            "facsimile_width": image_width,
            "facsimile_height": image_height,
            "total_lines": validation_results["total_lines"],
            "out_of_bounds_lines": validation_results["out_of_bounds_lines"],
            "out_of_bounds_paragraphs": validation_results["out_of_bounds_paragraphs"],
            "out_of_bounds_regions": validation_results["out_of_bounds_regions"],
            "pages_stats": page_stats,
            "cc": page_json.get("cc"),
        }
        entry.update(manifest_info)
        if self.git_version:
            entry["git_version"] = self.git_version

        return entry


def main(args: Optional[List[str]] = None) -> None:
    """
    Main function to run the Boundary Check Processor.

    Args:
        args: Command-line arguments (uses sys.argv if None)
    """
    options: argparse.Namespace = parse_arguments(args)

    processor: BoundaryCheckProcessor = BoundaryCheckProcessor(
        s3_path=options.s3_path,
        output=options.output,
        git_version=options.git_version,
        iiif_gallica_v3=options.iiif_gallica_v3,
        log_level=options.log_level,
        log_file=options.log_file,
    )

    # Log the parsed options after logger is configured
    log.info("%s", options)

    processor.run()
    log.info("Finished processing all pages.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"Processing error: {e}", exc_info=True)
        sys.exit(2)
