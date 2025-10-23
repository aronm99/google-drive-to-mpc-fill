# Google Drive to MPC Fill

This project contains Python scripts to extract card images from Google Drive folders and generate MPCFill XML files for creating custom Magic: The Gathering cards through MakePlayingCards.com.

## Files

1. **`google-drive-to-mpc-fill.py`** - Main script for extracting card images and generating MPCFill XML
2. **`requirements.txt`** - Python dependencies
3. **`outputs/`** - Directory containing generated XML files (ignored by Git)

## Workflow

1. **Extract Images**: Use the script to extract card images from Google Drive folders
2. **Generate XML**: Create MPCFill-compatible XML files in the `outputs/` directory
3. **Upload to MPC**: Use [MPC Autofill](https://github.com/chilli-axe/mpc-autofill/releases) to automatically upload images to MakePlayingCards.com

## Quick Start

### Basic Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Extract images and generate XML
python google-drive-to-mpc-fill.py "https://drive.google.com/drive/folders/1ABC123..."

# Generate XML with custom output file
python google-drive-to-mpc-fill.py --xml-output my-cards.xml "https://drive.google.com/drive/folders/1ABC123..."
```

### Using MPC Autofill

1. Download the latest release from [MPC Autofill](https://github.com/chilli-axe/mpc-autofill/releases)
2. Place the generated XML file from the `outputs/` directory into MPC Autofill
3. Run MPC Autofill to automatically upload images to MakePlayingCards.com

## Supported URL Formats

The scripts support various Google Drive URL formats:

- `https://drive.google.com/drive/folders/1ABC123...` (Folder)
- `https://drive.google.com/file/d/1XYZ789...` (File)
- `https://drive.google.com/open?id=1DEF456...` (Generic)
- `https://drive.google.com/drive/u/0/folders/1GHI789...` (With user ID)

## Examples

```bash
# Basic extraction and XML generation
python google-drive-to-mpc-fill.py "https://drive.google.com/drive/folders/1ABC123DEF456"

# Recursively process all subfolders
python google-drive-to-mpc-fill.py --recursive "https://drive.google.com/drive/folders/1ABC123DEF456"

# Generate XML with custom settings
python google-drive-to-mpc-fill.py --xml-output my-cards.xml --xml-foil "https://drive.google.com/drive/folders/1ABC123DEF456"

# Double-sided cards (front|back pairs)
python google-drive-to-mpc-fill.py --double-sided "front1.png|back1.png|front2.png|back2.png" --xml-output double-sided.xml "https://drive.google.com/drive/folders/1ABC123DEF456"

# Verbose mode with recursive processing
python google-drive-to-mpc-fill.py --verbose --recursive --xml-output all-cards.xml "https://drive.google.com/drive/folders/1ABC123DEF456"
```

## Features

- **Google Drive Integration**: Extract card images from public Google Drive folders
- **MPCFill XML Generation**: Create XML files compatible with MPC Autofill
- **Recursive Processing**: Automatically process subfolders with depth control
- **Double-Sided Cards**: Support for front/back card pairs
- **Custom Settings**: Configure card stock, foil options, and quantities
- **Multiple Extraction Methods**: Robust parsing with fallback methods
- **Duplicate Removal**: Automatically removes duplicate entries
- **Verbose Mode**: Detailed processing information

## XML Output

The script generates MPCFill-compatible XML files in the `outputs/` directory with:
- Card IDs from Google Drive
- Slot assignments for proper ordering
- Card names and metadata
- Support for double-sided cards
- Customizable card stock and foil options
- Automatic bracket sizing based on card count

## Limitations

- **Public Links Only**: Works best with publicly shared Google Drive links
- **Rate Limiting**: Google may limit requests if you make too many in a short time
- **Structure Changes**: Google Drive's HTML structure may change, affecting scraping reliability
- **Private Folders**: Private folders require authentication via Google Drive API
- **Image Quality**: Card images should be high resolution (800+ DPI recommended)

## Troubleshooting

1. **"Could not extract file/folder ID"**: Check that the URL is a valid Google Drive link
2. **"No files found"**: The folder might be private or the link might be invalid
3. **"Error accessing folder"**: Check your internet connection and try again
4. **Empty XML output**: The folder might be empty or contain only folders
5. **MPC Autofill errors**: Ensure XML files are in the correct format and images are accessible

## MPC Autofill Integration

This script generates XML files compatible with [MPC Autofill](https://github.com/chilli-axe/mpc-autofill/releases), which automates the process of uploading card images to MakePlayingCards.com.


## License

This project is provided as-is for educational and personal use.
