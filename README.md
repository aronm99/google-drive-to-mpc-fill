# Google Drive to MPC Fill

Extract card images from Google Drive folders and generate MPCFill XML files for creating custom Magic: The Gathering cards.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Extract images and generate XML
python google-drive-to-mpc-fill.py "https://drive.google.com/drive/folders/1ABC123..."

# Generate XML with custom output file
python google-drive-to-mpc-fill.py --output my-cards.xml "https://drive.google.com/drive/folders/1ABC123..."
```

### Supported URL Formats

- `https://drive.google.com/drive/folders/1ABC123...` (Folder)
- `https://drive.google.com/file/d/1XYZ789...` (File)
- `https://drive.google.com/open?id=1DEF456...` (Generic)

## Command Line Options

```bash
# Recursively process all subfolders
--recursive

# Maximum recursion depth (default: 5)
--max-depth 3

# Exclude specific folders
--exclude "temp,backup,old"

# Generate MPC XML output
--output cards.xml

# Card stock type
--stock "(S30) Standard Smooth"

# Enable foil cards
--foil

# The google drive file id for the cardback
--cardback "12RJeMQw2E0jEz4SwKJTItoONCeHD7skj"

# Double-sided cards (front|back pairs)
--double-sided "front1.png|back1.png;front2.png|back2.png"

# Multiple copies of specific cards
--card-multiples "card1.png|3;card2.png|2;frontCard.png|backCard.png"

# Verbose output
--verbose
```

## Examples

```bash
# Basic usage
python google-drive-to-mpc-fill.py "https://drive.google.com/drive/folders/1ABC123..."

# Recursive processing with XML output
python google-drive-to-mpc-fill.py --recursive --output cards.xml "https://drive.google.com/drive/folders/1ABC123..."

# Double-sided cards
python google-drive-to-mpc-fill.py --double-sided "front1.png|back1.png;front2.png|back2.png" --output double-sided.xml "https://drive.google.com/drive/folders/1ABC123..."

# Multiple copies of specific cards
python google-drive-to-mpc-fill.py --card-multiples "card1.png|3;card2.png|2;frontCard.png|backCard.png" --output multiples.xml "https://drive.google.com/drive/folders/1ABC123..."

# Combined features
python google-drive-to-mpc-fill.py --recursive --double-sided "front1.png|back1.png" --card-multiples "front1.png|2;back1.png|2" --output combined.xml "https://drive.google.com/drive/folders/1ABC123..."
```

## Combining Multiple XML Files

Use `combine-mpc-fill-files.py` to merge multiple MPC fill XML files into a single file:

```bash
# Combine two XML files (looks in outputs/ directory by default)
python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml

# Combine all XML files in outputs directory
python combine-mpc-fill-files.py outputs/*.xml -o combined.xml

# Or specify full paths
python combine-mpc-fill-files.py outputs/file1.xml outputs/file2.xml -o combined.xml

# Override stock type
python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --stock "(S33) Superior Smooth"

# Enable foil
python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --foil

# Override cardback ID
python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --cardback "YOUR_CARDBACK_ID"

# Disable automatic bracket calculation
python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --no-auto-bracket
```

### Combine Script Options

- `input_files`: Input XML files to combine (defaults to `outputs/` directory if no directory specified)
- `-o, --output`: Output XML file path (required, defaults to `outputs/` directory if no directory specified)
- `--stock`: Override stock type (e.g., "(S30) Standard Smooth", "(S33) Superior Smooth")
- `--foil`: Enable foil cards (overrides input files)
- `--no-foil`: Disable foil cards (overrides input files)
- `--cardback`: Override cardback Google Drive ID
- `--no-auto-bracket`: Disable automatic bracket calculation (uses maximum bracket from input files)

The script automatically:
- Combines all front cards and back cards from input files
- Renumbers slot numbers sequentially
- Calculates total quantity and appropriate bracket size
- Merges stock, foil, and cardback settings (uses first file's settings by default)

## Output

XML files are generated in the `outputs/` directory and are compatible with [MPC Autofill](https://github.com/chilli-axe/mpc-autofill/releases).
