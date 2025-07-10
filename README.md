# Impresso Make-Based Processing Template

This repository provides a template for creating new processing pipelines within the Impresso project ecosystem. It demonstrates best practices for building scalable, distributed newspaper processing workflows using Make, Python, and S3 storage.

## Table of Contents

- [Overview](#overview)
- [Template Structure](#template-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Processing a Single Newspaper](#processing-a-single-newspaper)
- [Build System](#build-system)
- [Contributing](#contributing)
- [About Impresso](#about-impresso)

## Overview

This template provides a complete framework for building newspaper processing pipelines that:

- **Scale Horizontally**: Process data across multiple machines without conflicts
- **Handle Large Datasets**: Efficiently process large collections using S3 and local stamp files
- **Maintain Consistency**: Ensure reproducible results with proper dependency management
- **Support Parallel Processing**: Utilize multi-core systems and distributed computing
- **Integrate with S3**: Seamlessly work with both local files and S3 storage

## Template Structure

```
├── README.md                   # This file
├── Makefile                    # Main build configuration
├── .env                        # Environment variables (create manually from dotenv.sample)
├── dotenv.sample               # Sample environment configuration
├── Pipfile                     # Python dependencies
├── lib/
│   └── cli_TEMPLATE.py         # Template CLI script
├── cookbook/                   # Build system components
│   ├── README.md               # Detailed cookbook documentation
│   ├── setup_TEMPLATE.mk       # Template-specific setup
│   ├── paths_TEMPLATE.mk       # Path definitions
│   ├── sync_TEMPLATE.mk        # Data synchronization
│   ├── processing_TEMPLATE.mk  # Processing targets
│   └── ...                     # Other cookbook components
└── build.d/                    # Local build directory (auto-created)
```

## Quick Start

Follow these steps to get started with the template:

### 1. Prerequisites

Ensure you have the required system dependencies installed:

**Ubuntu/Debian:**

```bash
sudo apt-get update
sudo apt-get install -y make git git-lfs parallel coreutils python3 python3-pip
```

**macOS:**

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install make git git-lfs parallel coreutils python3
```

**System Requirements:**

- Python 3.11+
- Make (GNU Make recommended)
- Git with git-lfs
- AWS CLI (optional, for direct S3 access)

### 2. Clone and Setup

1. **Clone the repository:**

   ```bash
   git clone --recursive <your-template-repo>
   cd impresso-cookbook-template
   ```

2. **Configure environment:**

   ```bash
   cp dotenv.sample .env
   # Edit .env with your S3 credentials (see Configuration section below)
   ```

3. **Install Python dependencies:**

   ```bash
   # Using pipenv (recommended)
   pipenv install

   # Or using pip directly
   python3 -m pip install -r requirements.txt
   ```

4. **Initialize the environment:**
   ```bash
   make setup
   ```

### 3. Adapt the Template to your new Processing Pipeline

There is a special make target that will copy the template files to prepare your new
processing pipeline.
You need to decide on the cookbook acronym of your new pipeline. The following command
will copy all files under cookbook to and replace TEMPLATE with your acronym.

```bash
export PROCESSING_ACRONYM=myimpressopipeline
make -f cookbook/template-starter.mk
```

### 4. Verify Installation

Test your setup with a quick help command:

```bash
make help
```

You should see available targets and configuration options.

### 5. Run a Test

Process a small newspaper to verify everything works:

```bash
# Test with a smaller newspaper first
make newspaper NEWSPAPER=actionfem
```

### 6. Explore Available Commands

Once installation is verified, explore the build system:

```bash
# Show all available targets
make
```

## Configuration

Before running any processing, configure your environment:

### Required Environment Variables

Edit your `.env` file with these required settings:

```bash
# S3 Configuration (required)
SE_ACCESS_KEY=your_s3_access_key
SE_SECRET_KEY=your_s3_secret_key
SE_HOST_URL=https://os.zhdk.cloud.switch.ch/

# Logging Configuration (optional)
LOGGING_LEVEL=INFO
```

### Optional Processing Variables

These can be set in `.env` or passed as command arguments:

- `NEWSPAPER`: Target newspaper to process
- `BUILD_DIR`: Local build directory (default: `build.d`)
- `PARALLEL_JOBS`: Number of parallel jobs (auto-detected)
- `COLLECTION_JOBS`: Number of parallel newspaper collections
- `NEWSPAPER_YEAR_SORTING`: Processing order (`shuf` for random, `cat` for chronological)

### S3 Bucket Configuration

Configure S3 buckets in your paths file:

- `S3_BUCKET_REBUILT`: Input data bucket (default: `22-rebuilt-final`)
- `S3_BUCKET_TEMPLATE`: Output data bucket (default: `140-processed-data-sandbox`)

## Processing a Single Newspaper

### Basic Processing

Process a single newspaper (all years) with default settings:

```bash
make newspaper NEWSPAPER=actionfem
```

### Step-by-Step Processing

You can also run individual steps:

1. **Sync data:**

   ```bash
   make sync NEWSPAPER=actionfem
   ```

2. **Run processing:**

   ```bash
   make processing-target NEWSPAPER=actionfem
   ```

## Build System

### Core Targets

After installation, these are the main commands you'll use:

- `make help`: Show available targets and current configuration
- `make setup`: Initialize environment (run once after installation)
- `make newspaper`: Process single newspaper
- `make collection`: Process multiple newspapers in parallel
- `make all`: Complete processing pipeline with data sync

### Data Management

- `make sync`: Sync input and output data
- `make sync-input`: Download input data from S3
- `make sync-output`: Upload results to S3 (will never overwrite existing data)
- `make clean-build`: Remove build directory

### Parallel Processing

The system automatically detects CPU cores and configures parallel processing:

```bash
# Process collection with custom parallelization
make collection COLLECTION_JOBS=4 MAX_LOAD=8
```

### Build System Architecture

The build system uses:

- **Stamp Files**: Track processing state without downloading full datasets
- **S3 Integration**: Direct processing from/to S3 storage
- **Distributed Processing**: Multiple machines can work independently
- **Dependency Management**: Automatic dependency resolution via Make

For detailed build system documentation, see [cookbook/README.md](cookbook/README.md).

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `make newspaper NEWSPAPER=actionfem`
5. Submit a pull request

## About Impresso

### Impresso Project

[Impresso - Media Monitoring of the Past](https://impresso-project.ch) is an interdisciplinary research project that aims to develop and consolidate tools for processing and exploring large collections of media archives across modalities, time, languages and national borders.

The project is funded by:

- Swiss National Science Foundation (grants [CRSII5_173719](http://p3.snf.ch/project-173719) and [CRSII5_213585](https://data.snf.ch/grants/grant/213585))
- Luxembourg National Research Fund (grant 17498891)

### Copyright

Copyright (C) 2024 The Impresso team.

### License

This program is provided as open source under the [GNU Affero General Public License](https://github.com/impresso/impresso-pyindexation/blob/master/LICENSE) v3 or later.

---

<p align="center">
  <img src="https://github.com/impresso/impresso.github.io/blob/master/assets/images/3x1--Yellow-Impresso-Black-on-White--transparent.png?raw=true" width="350" alt="Impresso Project Logo"/>
</p>
