#!/usr/bin/env python3
"""
Page Statistics CLI Script

This module provides functionality to compute statistics from JSON files
representing document structures. It calculates metrics such as the number
of regions, paragraphs, lines, and empty lines, as well as averages for
paragraphs and lines per region or paragraph.

The script follows the Impresso project CLI template pattern with support for:
- Smart I/O operations (local files and S3 URIs)
- Comprehensive logging configuration
- S3 integration with automatic client setup
- Command-line interface with proper error handling
- Processor class architecture for maintainable code

Example:
    $ python page_statistics.py -i input.json -o output.jsonl --log-level INFO
    $ python page_statistics.py -i s3://bucket/input.json -o s3://bucket/output.jsonl
"""

import logging
import argparse
import json
import sys
from smart_open import open as smart_open  # type: ignore
from typing import List, Optional, Dict, Any

from impresso_cookbook import (  # type: ignore
    get_s3_client,
    get_timestamp,
    setup_logging,
    get_transport_params,
)
import numpy as np

log = logging.getLogger(__name__)


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
            "Compute statistics from JSON files representing document structures."
        )
    )
    parser.add_argument(
        "--log-file", dest="log_file", help="Write log to FILE", metavar="FILE"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: %(default)s)",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        help="Input JSON file (required)",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Output JSONL file (required)",
        required=True,
    )
    return parser.parse_args(args)


class PageStatisticsProcessor:
    """
    A processor class that computes statistics from JSON document structures.
    """

    def __init__(
        self,
        input_file: str,
        output_file: str,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
    ) -> None:
        """
        Initializes the PageStatisticsProcessor with explicit parameters.

        Args:
            input_file (str): Path to the input JSON file
            output_file (str): Path to the output JSONL file
            log_level (str): Logging level (default: "INFO")
            log_file (Optional[str]): Path to log file (default: None)
        """
        self.input_file = input_file
        self.output_file = output_file
        self.log_level = log_level
        self.log_file = log_file

        # Configure the module-specific logger
        setup_logging(self.log_level, self.log_file, logger=log)

        # Initialize S3 client and timestamp
        self.s3_client = get_s3_client()
        self.timestamp = get_timestamp()

    def run(self) -> None:
        """
        Runs the page statistics processor, reading from the input file
        and computing statistics.
        """
        try:
            with smart_open(
                self.input_file,
                "r",
                encoding="utf-8",
                transport_params=get_transport_params(self.input_file),
            ) as f:
                json_data = json.load(f)

            stats = self.compute_statistics(json_data)
            stats["timestamp"] = self.timestamp

            with smart_open(
                self.output_file,
                "w",
                encoding="utf-8",
                transport_params=get_transport_params(self.output_file),
            ) as output_stream:
                output_stream.write(json.dumps(stats, ensure_ascii=False) + "\n")

        except Exception as e:
            log.error("Error processing file: %s", e, exc_info=True)
            sys.exit(1)

    def compute_statistics(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute statistics from the given JSON data.

        Args:
            json_data (Dict[str, Any]): The JSON data containing document structure.

        Returns:
            Dict[str, Any]: A dictionary containing computed statistics.
        """
        # Detect reversed adjacent lines in paragraphs
        para_counter = 0
        for region in json_data["r"]:
            for para in region["p"]:
                para_counter += 1
                filtered_lines = [
                    line for line in para["l"] if "c" in line and len(line["c"]) >= 4
                ]
                for idx in range(1, len(filtered_lines)):
                    prev_c = filtered_lines[idx - 1]["c"]
                    curr_c = filtered_lines[idx]["c"]
                    if curr_c[1] + curr_c[3] < prev_c[1]:
                        log.warning(
                            "Paragraph %d has reversed line order between lines"
                            " %d and %d: prev top y=%s, next bottom"
                            " y=%s",
                            para_counter,
                            idx - 1,
                            idx,
                            prev_c[1],
                            curr_c[1] + curr_c[3],
                        )

        for region in json_data["r"]:
            for para in region["p"]:
                for line in para["l"]:
                    line["text"] = extract_line_text(line)

        num_regions = len(json_data["r"])
        num_paragraphs = sum(
            len(region["p"]) for region in json_data["r"] if "p" in region
        )
        num_lines = sum(
            len(paragraph["l"])
            for region in json_data["r"]
            for paragraph in region["p"]
        )
        num_empty_lines = sum(
            1
            for region in json_data["r"]
            for paragraph in region["p"]
            for line in paragraph["l"]
            if line == [] or len(line["text"]) == 0
        )

        avg_paragraphs_per_region = (
            round(num_paragraphs / num_regions, 2) if num_regions > 0 else 0
        )
        avg_lines_per_region = (
            round(num_lines / num_regions, 2) if num_regions > 0 else 0
        )
        avg_lines_per_paragraph = (
            round(num_lines / num_paragraphs, 2) if num_paragraphs > 0 else 0
        )

        line_widths = [
            line["c"][2]
            for region in json_data["r"]
            for paragraph in region["p"]
            for line in paragraph["l"]
            if "c" in line
        ]
        line_width_stats = compute_descriptive_statistics(line_widths)

        line_heights = [
            line["c"][3]
            for region in json_data["r"]
            for paragraph in region["p"]
            for line in paragraph["l"]
            if isinstance(line, dict)
            and "c" in line
            and len(line["c"]) >= 4
            and line.get("t")
        ]
        line_height_stats = compute_descriptive_statistics(line_heights)

        # Compute largest paragraph coordinates
        max_area = 0
        largest_coords = {}
        for region in json_data["r"]:
            for para in region["p"]:
                coords_list = [
                    line["c"]
                    for line in para["l"]
                    if "c" in line and len(line["c"]) >= 4
                ]
                if not coords_list:
                    continue
                min_x = min(c[0] for c in coords_list)
                min_y = min(c[1] for c in coords_list)
                max_x = max(c[0] + c[2] for c in coords_list)
                max_y = max(c[1] + c[3] for c in coords_list)
                area = (max_x - min_x) * (max_y - min_y)
                if area > max_area:
                    max_area = area
                    largest_coords = {
                        "x": min_x,
                        "y": min_y,
                        "width": max_x - min_x,
                        "height": max_y - min_y,
                    }
        log.info("Largest paragraph coordinates: %s", largest_coords)

        # Compute paragraph coverage percentages
        paragraph_coverages = []
        para_coverage_counter = 0
        for region in json_data["r"]:
            for para in region["p"]:
                para_coverage_counter += 1
                coords_list = [
                    line["c"]
                    for line in para["l"]
                    if "c" in line and len(line["c"]) >= 4
                ]
                if not coords_list:
                    continue
                min_x = min(c[0] for c in coords_list)
                min_y = min(c[1] for c in coords_list)
                max_x = max(c[0] + c[2] for c in coords_list)
                max_y = max(c[1] + c[3] for c in coords_list)
                total_line_area = sum(c[2] * c[3] for c in coords_list)
                bounding_area = (max_x - min_x) * (max_y - min_y)
                coverage = (
                    round(total_line_area / bounding_area * 100, 2)
                    if bounding_area > 0
                    else 0
                )
                if coverage < 80:
                    log.warning(
                        "Paragraph %d coverage below 80%%: %s%% at x=%s,"
                        " y=%s, width=%s, height=%s",
                        para_coverage_counter,
                        coverage,
                        min_x,
                        min_y,
                        max_x - min_x,
                        max_y - min_y,
                    )
                if coverage < 70:
                    line_texts = [line.get("text", "") for line in para["l"]]
                    log.debug(
                        "Paragraph %d coverage below 70%%, emitting line texts:",
                        para_coverage_counter,
                    )
                    for text in line_texts:
                        log.debug(text)
                paragraph_coverages.append(
                    {
                        "coords": {
                            "x": min_x,
                            "y": min_y,
                            "width": max_x - min_x,
                            "height": max_y - min_y,
                        },
                        "coverage_percent": coverage,
                    }
                )

        return {
            "num_regions": num_regions,
            "num_paragraphs": num_paragraphs,
            "num_lines": num_lines,
            "num_empty_lines": num_empty_lines,
            "avg_paragraphs_per_region": avg_paragraphs_per_region,
            "avg_lines_per_region": avg_lines_per_region,
            "avg_lines_per_paragraph": avg_lines_per_paragraph,
            "line_width_stats": line_width_stats,
            "line_height_stats": line_height_stats,
            "paragraph_coverages": paragraph_coverages,
        }


def extract_line_text(line: Dict[str, Any]) -> str:
    """
    Extract the concatenated text from a line.

    Args:
        line (Dict[str, Any]): The line data containing text segments.

    Returns:
        str: The concatenated text of the line.
    """
    if isinstance(line, dict) and "t" in line:
        return " ".join(
            segment["tx"] for segment in line["t"] if segment.get("tx")
        ).strip()
    return ""


def compute_descriptive_statistics(values: list) -> Dict[str, Any]:
    """
    Compute descriptive statistics for a sequence of values.

    Args:
        values (list): A list of numerical values.

    Returns:
        Dict[str, Any]: A dictionary containing descriptive statistics.
    """
    if not values:
        return {
            "count": 0,
            "mean": 0,
            "median": 0,
            "mode": None,
            "min": 0,
            "max": 0,
            "range": 0,
            "variance": 0,
            "std_dev": 0,
            "skewness": 0,
            "kurtosis": 0,
        }

    count = len(values)
    mean = round(np.mean(values), 2)
    median = round(np.median(values), 2)
    mode = max(set(values), key=values.count) if values else None
    min_value = min(values)
    max_value = max(values)
    value_range = max_value - min_value
    variance = round(np.var(values, ddof=1), 2)
    std_dev = round(np.std(values, ddof=1), 2)
    skewness = round((3 * (mean - median)) / std_dev, 2) if std_dev != 0 else 0

    # Fix numpy array operation
    values_array = np.array(values)
    kurtosis = (
        round(np.mean((values_array - mean) ** 4) / (std_dev**4) - 3, 2)
        if std_dev != 0
        else 0
    )

    return {
        "count": count,
        "mean": mean,
        "median": median,
        "mode": mode,
        "min": min_value,
        "max": max_value,
        "range": value_range,
        "variance": variance,
        "std_dev": std_dev,
        "skewness": skewness,
        "kurtosis": kurtosis,
    }


def main(args: Optional[List[str]] = None) -> None:
    """
    Main function to run the Page Statistics Processor.

    Args:
        args: Command-line arguments (uses sys.argv if None)
    """
    options: argparse.Namespace = parse_arguments(args)

    processor: PageStatisticsProcessor = PageStatisticsProcessor(
        input_file=options.input,
        output_file=options.output,
        log_level=options.log_level,
        log_file=options.log_file,
    )

    # Log the parsed options after logger is configured
    log.info("%s", options)

    processor.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error("Processing error: %s", e, exc_info=True)
        sys.exit(2)
