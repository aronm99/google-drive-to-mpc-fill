# Google Drive File Lister

This project contains Python scripts to list files and directories from public Google Drive links.

## Files

1. **`mpc-xml-generator.py`** - Original script with Google Drive API integration (requires authentication)
2. **`google_drive_lister.py`** - Enhanced script using web scraping (works with public links)
3. **`requirements.txt`** - Python dependencies

## Quick Start

### For Public Google Drive Links (Recommended)

```bash
# Install dependencies
pip install requests beautifulsoup4 lxml

# Run the script
python google_drive_lister.py "https://drive.google.com/drive/folders/1ABC123..."
```

### For Authenticated Access (Advanced)

```bash
# Install all dependencies
pip install -r requirements.txt

# Run the original script (requires Google Cloud setup)
python mpc-xml-generator.py "https://drive.google.com/drive/folders/1ABC123..."
```

## Supported URL Formats

The scripts support various Google Drive URL formats:

- `https://drive.google.com/drive/folders/1ABC123...` (Folder)
- `https://drive.google.com/file/d/1XYZ789...` (File)
- `https://drive.google.com/open?id=1DEF456...` (Generic)
- `https://drive.google.com/drive/u/0/folders/1GHI789...` (With user ID)

## Examples

```bash
# List folder contents (non-recursive)
python google-drive-to-mpc-fill.py "https://drive.google.com/drive/folders/1ABC123DEF456"

# Recursively process all subfolders
python google-drive-to-mpc-fill.py --recursive "https://drive.google.com/drive/folders/1ABC123DEF456"

# Recursive with custom depth limit
python google-drive-to-mpc-fill.py --recursive --max-depth 3 "https://drive.google.com/drive/folders/1ABC123DEF456"

# Verbose recursive mode (shows processing details)
python google-drive-to-mpc-fill.py --verbose --recursive "https://drive.google.com/drive/folders/1ABC123DEF456"

# Get file information
python google-drive-to-mpc-fill.py "https://drive.google.com/file/d/1XYZ789ABC123"
```

## Enhanced Features

The updated scraper now includes:
- **Multiple extraction methods**: Script tags, data attributes, HTML elements, meta tags
- **Google Drive ID extraction**: Shows the unique ID for each file/folder
- **Duplicate removal**: Automatically removes duplicate entries
- **Verbose mode**: Shows detailed extraction information
- **Better error handling**: More robust parsing with fallback methods
- **🆕 Recursive folder traversal**: Automatically processes subfolders
- **🆕 Path tracking**: Shows folder hierarchy in recursive mode
- **🆕 Depth control**: Configurable maximum recursion depth

## Output Format

The script displays:
- 📁 Folders (with count and Google Drive IDs)
- 📄 Files (with size information and Google Drive IDs)
- Total counts
- Error messages for inaccessible content
- Verbose extraction details (when using --verbose flag)
- **🆕 Folder hierarchy paths** (when using --recursive flag)
- **🆕 Recursion depth information** (when using --recursive flag)

## Limitations

- **Public Links Only**: The web scraping version works best with publicly shared Google Drive links
- **Rate Limiting**: Google may limit requests if you make too many in a short time
- **Structure Changes**: Google Drive's HTML structure may change, affecting scraping reliability
- **Private Folders**: Private folders require authentication via Google Drive API

## Troubleshooting

1. **"Could not extract file/folder ID"**: Check that the URL is a valid Google Drive link
2. **"No files found"**: The folder might be private or the link might be invalid
3. **"Error accessing folder"**: Check your internet connection and try again
4. **Empty results**: The folder might be empty or the scraping method might need updates

## Google Drive API Setup (For Advanced Users)

If you need to access private folders, you'll need to set up Google Drive API:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Drive API
4. Create credentials (OAuth 2.0 Client ID)
5. Download `credentials.json` to your project directory
6. Run the script and authenticate when prompted

## License

This project is provided as-is for educational and personal use.
