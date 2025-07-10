# impresso-cookbook-template

This project provides a template for creating command-line interface (CLI) scripts within the Impresso ecosystem. It demonstrates best practices for file I/O operations, logging configuration, S3 integration, and error handling.

## Project Structure

```
impresso-cookbook-template
├── lib
│   └── cli_TEMPLATE.py       # Template for CLI scripts
├── pyrightconfig.json        # Configuration for Pyright type checker
└── README.md                 # Project documentation
```

## Features

- **File I/O Operations**: Utilizes `smart_open` for seamless handling of both local files and S3 URIs.
- **Logging Configuration**: Integrates with a logging setup for consistent logging across tools.
- **S3 Integration**: Automatically configures S3 client connections using environment variables.
- **Command-line Interface**: Follows `argparse` patterns with proper type hints and documentation.
- **Error Handling**: Implements robust error handling with logging for file processing failures.

## Usage

To use the CLI template, copy `lib/cli_TEMPLATE.py` and modify the `TemplateProcessor` class to implement specific logic. Update command-line arguments in the `parse_arguments()` function as needed.

### Example Command

```bash
python cli.py -i input.txt --log-level DEBUG --log-file process.log
```

## Installation

Ensure you have the required dependencies installed. You can install them using pip:

```bash
pip install -r requirements.txt
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.