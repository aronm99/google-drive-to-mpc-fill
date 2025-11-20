#!/usr/bin/env python3
"""
Google Drive File Lister - Enhanced Version

This script takes a Google Drive link and lists all files and directories
in the shared folder or displays information about a single file.

Supports:
- Folder sharing links
- File sharing links  
- Direct Google Drive URLs
- Public links without authentication (using web scraping)

Requirements:
- requests
- beautifulsoup4
- lxml (optional, for better HTML parsing)
- selenium (optional, for handling lazy-loaded content)

Note: Selenium is used by default to scroll and load all lazy-loaded content. Use --use-raw-html for faster raw HTML scraping (may miss lazy-loaded files).
"""

import re
import sys
import argparse
import json
import csv
import os
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

DEFAULT_BRACKET_SIZE = [18, 36, 55, 72, 90, 108, 126, 144, 162, 180, 198, 216, 234, 396, 504, 612]

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing required packages. Please install them with:")
    print(f"pip install requests beautifulsoup4 lxml")
    sys.exit(1)

# Selenium is optional - only needed for lazy-loaded content
SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    pass

class GoogleDriveLister:
    def __init__(self, use_selenium: bool = True):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.bracket_sizes = DEFAULT_BRACKET_SIZE
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.driver = None
    
    def _find_next_bracket(self, quantity: int) -> int:
        """Find the next largest bracket size for the given quantity"""
        for bracket in self.bracket_sizes:
            if bracket >= quantity:
                return bracket
        
        # If quantity exceeds all brackets, return the largest one
        return self.bracket_sizes[-1] if self.bracket_sizes else quantity
    
    def extract_file_id(self, url: str) -> Optional[str]:
        """Extract file/folder ID from various Google Drive URL formats"""
        patterns = [
            r'/file/d/([a-zA-Z0-9_-]+)',
            r'/folders/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'/([a-zA-Z0-9_-]{25,})',  # Generic pattern for Google Drive IDs
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def normalize_url(self, url: str) -> str:
        """Normalize Google Drive URL to a standard format"""
        file_id = self.extract_file_id(url)
        if not file_id:
            return url
        
        # Convert to folder view URL for easier processing
        return f"https://drive.google.com/drive/folders/{file_id}"
    
    def _is_folder(self, item: Dict) -> bool:
        """Enhanced folder detection logic based on actual Google Drive data"""
        # Check mimeType first - this is the most reliable indicator
        mime_type = item.get('mimeType', '').lower()
        if mime_type == 'application/vnd.google-apps.folder':
            return True
        
        # Check if explicitly marked as folder
        if item.get('isFolder', False):
            return True
        
        # Check data-target attribute
        if item.get('data-target') == 'folder':
            return True
        
        # Check class names for folder indicators
        classes = item.get('class', [])
        if isinstance(classes, list):
            for class_name in classes:
                if 'folder' in class_name.lower():
                    return True
        
        # Check href for folder indicators
        href = item.get('href', '')
        if '/folders/' in href:
            return True
        
        # Check aria-label for folder/file indicators
        aria_label = item.get('aria-label', '').lower()
        if 'shared folder' in aria_label:
            return True
        elif 'image' in aria_label and 'more info' in aria_label:
            # This is a file with an image preview
            return False
        
        # NEW: Check for image tags - files with previews have image tags, folders typically don't
        if item.get('has_image_preview', False):
            return False
        
        # Special case: Check if it's a Google Doc that might be a folder
        # Some Google Drive folders are represented as Google Docs
        if mime_type == 'application/vnd.google-apps.document' or item.get('data-target') == 'doc':
            # If it has no file extension and looks like a folder name, it might be a folder
            name = item.get('name', '').lower()
            # Check if it has a file extension - if it does, it's likely a file, not a folder
            if any(name.endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.txt', '.zip', '.rar', '.mp4', '.mp3', '.avi', '.mov', '.gif', '.bmp', '.tiff', '.svg', '.xlsx', '.pptx', '.csv', '.json', '.xml', '.html', '.css', '.js', '.py', '.java', '.cpp', '.c', '.h']):
                # This has a file extension, so it's likely a file, not a folder
                return False
            # If no file extension, it could be a folder represented as a Google Doc
            return True
        
        return False
    
    def _debug_item(self, item: Dict, verbose: bool = False) -> None:
        """Debug helper to show item data when verbose mode is enabled"""
        if verbose:
            print(f"    DEBUG Item: {item.get('name', 'Unknown')}")
            print(f"      - mimeType: {item.get('mimeType', 'None')}")
            print(f"      - isFolder: {item.get('isFolder', 'None')}")
            print(f"      - data-target: {item.get('data-target', 'None')}")
            print(f"      - class: {item.get('class', 'None')}")
            print(f"      - href: {item.get('href', 'None')}")
            print(f"      - aria-label: {item.get('aria-label', 'None')}")
            print(f"      - Detected as folder: {self._is_folder(item)}")
            print()
    
    def _get_page_with_selenium(self, url: str, verbose: bool = False) -> Optional[bytes]:
        """Use Selenium to load page and scroll to load all lazy-loaded content"""
        if not SELENIUM_AVAILABLE:
            if verbose:
                print("  Selenium not available. Install with: pip install selenium")
            return None
        
        try:
            # Initialize driver if not already done
            if self.driver is None:
                try:
                    # Try Chrome first
                    options = webdriver.ChromeOptions()
                    options.add_argument('--headless')
                    options.add_argument('--no-sandbox')
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-gpu')
                    options.add_argument('--window-size=1920,1080')
                    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
                    self.driver = webdriver.Chrome(options=options)
                except Exception as e:
                    if verbose:
                        print(f"  Could not initialize Chrome driver: {e}")
                        print("  Trying Firefox...")
                    try:
                        options = webdriver.FirefoxOptions()
                        options.add_argument('--headless')
                        self.driver = webdriver.Firefox(options=options)
                    except Exception as e2:
                        if verbose:
                            print(f"  Could not initialize Firefox driver: {e2}")
                        return None
            
            if verbose:
                print("  Loading page with Selenium...")
            
            # Load the page
            self.driver.get(url)
            
            # Wait for initial content to load
            time.sleep(3)
            
            if verbose:
                print("  Scrolling to load all content...")
            
            # Try multiple strategies to find scroll containers
            scroll_containers = []
            scroll_selectors = [
                'c-wiz',  # Google's custom element for dynamic content containers
                'c-wiz[jsname]',  # c-wiz with jsname attribute
                '[role="main"]',
                '[data-view-type="1"]',
                'div[role="grid"]',
                'div[role="listbox"]',
                'div[data-view-type]',
                'div[style*="overflow"]',
                'div[style*="overflow-y"]',
                'table tbody',
                '.a-s-fa-Ha-pa',
                'div[jsname]'
            ]
            
            if verbose:
                print("  Searching for scrollable containers...")
            
            for selector in scroll_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if verbose and elements:
                        print(f"    Found {len(elements)} element(s) with selector: {selector}")
                    
                    for element in elements:
                        try:
                            # Check if element is scrollable
                            scroll_height = self.driver.execute_script("return arguments[0].scrollHeight;", element)
                            client_height = self.driver.execute_script("return arguments[0].clientHeight;", element)
                            is_scrollable = scroll_height > client_height
                            
                            if verbose:
                                tag_name = self.driver.execute_script("return arguments[0].tagName;", element)
                                element_id = element.get_attribute('id') or 'no-id'
                                element_class = element.get_attribute('class') or 'no-class'
                                print(f"      Element: <{tag_name}> id='{element_id}' class='{element_class[:50]}...'")
                                print(f"        scrollHeight: {scroll_height}, clientHeight: {client_height}, scrollable: {is_scrollable}")
                            
                            if is_scrollable:
                                scroll_containers.append(element)
                                if verbose:
                                    print(f"        -> Added to scroll containers list")
                        except Exception as e:
                            if verbose:
                                print(f"        -> Error checking element: {e}")
                            continue
                except Exception as e:
                    if verbose:
                        print(f"    Error with selector '{selector}': {e}")
                    continue
            
            if verbose:
                print(f"  Found {len(scroll_containers)} scrollable container(s)")
                print(f"  Adding window/document as fallback scroll target")
            
            # Also try window/document scrolling
            scroll_containers.append(None)  # None means scroll window
            if verbose:
                print(f"  Total scroll targets: {len(scroll_containers)} (including window)")
            
            # Count file elements using multiple selectors
            def count_files():
                """Count files using multiple selector strategies"""
                counts = []
                selectors = [
                    '[data-id]',
                    '[data-target="file"]',
                    '[data-target="folder"]',
                    'div[data-id]',
                    'tr[data-id]',
                    '[role="row"]',
                    'div[jsname][data-id]'
                ]
                for selector in selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        counts.append(len(elements))
                    except:
                        continue
                return max(counts) if counts else 0
            
            # Count initial files
            last_count = count_files()
            if verbose:
                print(f"  Initial file count: {last_count}")
            
            # Scroll strategy: incremental scrolling works better than jumping to bottom
            scroll_attempts = 0
            max_scroll_attempts = 100  # Increased for large folders
            no_change_count = 0
            max_no_change = 5  # Increased threshold
            
            while scroll_attempts < max_scroll_attempts:
                if verbose:
                    print(f"  Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}")
                
                # Try scrolling each container
                scrolled = False
                for idx, container in enumerate(scroll_containers):
                    try:
                        if container is None:
                            # Scroll window incrementally
                            current_scroll = self.driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop;")
                            max_scroll = self.driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                            # Scroll down by viewport height
                            scroll_amount = self.driver.execute_script("return window.innerHeight;")
                            new_scroll = min(current_scroll + scroll_amount, max_scroll)
                            
                            if verbose:
                                print(f"    Scrolling window: {current_scroll} -> {new_scroll} (max: {max_scroll})")
                            
                            self.driver.execute_script(f"window.scrollTo(0, {new_scroll});")
                            scrolled = True
                        else:
                            # Scroll container incrementally
                            current_scroll = self.driver.execute_script("return arguments[0].scrollTop;", container)
                            max_scroll = self.driver.execute_script("return arguments[0].scrollHeight;", container)
                            client_height = self.driver.execute_script("return arguments[0].clientHeight;", container)
                            # Scroll down by container height
                            new_scroll = min(current_scroll + client_height, max_scroll)
                            
                            if verbose:
                                tag_name = self.driver.execute_script("return arguments[0].tagName;", container)
                                print(f"    Scrolling container #{idx} (<{tag_name}>): {current_scroll} -> {new_scroll} (max: {max_scroll}, client: {client_height})")
                            
                            self.driver.execute_script("arguments[0].scrollTop = arguments[1];", container, new_scroll)
                            scrolled = True
                    except Exception as e:
                        if verbose:
                            print(f"    Error scrolling container #{idx}: {e}")
                        continue
                
                if not scrolled:
                    # Fallback: scroll window
                    if verbose:
                        print(f"    No container scrolled, using fallback window scroll")
                    self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
                
                # Wait for content to load (longer wait for Google Drive)
                time.sleep(2)
                
                # Count files again
                current_count = count_files()
                
                if verbose:
                    if current_count != last_count:
                        print(f"  File count changed: {last_count} -> {current_count} (+{current_count - last_count})")
                    else:
                        print(f"  File count unchanged: {current_count} (no change count: {no_change_count})")
                
                if current_count == last_count:
                    no_change_count += 1
                    if no_change_count >= max_no_change:
                        if verbose:
                            print(f"  No new files loaded after {no_change_count} scroll attempts (found {current_count} files)")
                        # Try one more aggressive scroll to bottom
                        if scroll_attempts < max_scroll_attempts - 1:
                            if verbose:
                                print(f"  Attempting aggressive scroll to bottom...")
                            for idx, container in enumerate(scroll_containers):
                                try:
                                    if container is None:
                                        max_scroll = self.driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                                        if verbose:
                                            print(f"    Scrolling window to bottom: {max_scroll}")
                                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                    else:
                                        max_scroll = self.driver.execute_script("return arguments[0].scrollHeight;", container)
                                        tag_name = self.driver.execute_script("return arguments[0].tagName;", container)
                                        if verbose:
                                            print(f"    Scrolling container #{idx} (<{tag_name}>) to bottom: {max_scroll}")
                                        self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                                except Exception as e:
                                    if verbose:
                                        print(f"    Error in aggressive scroll for container #{idx}: {e}")
                                    continue
                            time.sleep(3)
                            current_count = count_files()
                            if verbose:
                                print(f"  File count after aggressive scroll: {current_count}")
                            if current_count == last_count:
                                if verbose:
                                    print(f"  No additional files found, stopping scroll attempts")
                                break
                            else:
                                no_change_count = 0
                                if verbose:
                                    print(f"  Found more files after aggressive scroll: {current_count} (+{current_count - last_count})")
                        else:
                            break
                else:
                    no_change_count = 0
                    last_count = current_count
                
                scroll_attempts += 1
            
            # Final scroll to bottom to catch any remaining files
            if verbose:
                print(f"  Performing final scroll to bottom...")
            for idx, container in enumerate(scroll_containers):
                try:
                    if container is None:
                        max_scroll = self.driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                        if verbose:
                            print(f"    Final window scroll to: {max_scroll}")
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    else:
                        max_scroll = self.driver.execute_script("return arguments[0].scrollHeight;", container)
                        tag_name = self.driver.execute_script("return arguments[0].tagName;", container)
                        if verbose:
                            print(f"    Final container #{idx} (<{tag_name}>) scroll to: {max_scroll}")
                        self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                except Exception as e:
                    if verbose:
                        print(f"    Error in final scroll for container #{idx}: {e}")
                    continue
            time.sleep(2)
            
            # Final count
            final_count = count_files()
            if verbose:
                print(f"  Final file count: {final_count}")
            
            # Scroll back to top
            if verbose:
                print(f"  Scrolling back to top...")
            for idx, container in enumerate(scroll_containers):
                try:
                    if container is None:
                        self.driver.execute_script("window.scrollTo(0, 0);")
                    else:
                        self.driver.execute_script("arguments[0].scrollTop = 0;", container)
                except Exception as e:
                    if verbose:
                        print(f"    Error scrolling container #{idx} to top: {e}")
                    continue
            time.sleep(1)
            
            if verbose:
                print(f"  Finished scrolling after {scroll_attempts} attempts")
                print(f"  Summary: Found {len(scroll_containers)} scroll target(s), {final_count} total files")
            
            # Try to extract files directly from DOM before getting HTML
            # This can be more reliable than parsing HTML
            direct_files = self._extract_files_from_selenium_dom(verbose)
            if direct_files and verbose:
                print(f"  Extracted {len(direct_files)} files directly from DOM")
            
            # Get the page source
            html_content = self.driver.page_source.encode('utf-8')
            
            # Store direct files for later use if needed
            if direct_files:
                # We'll inject these into the HTML as a comment so they can be extracted
                # This is a workaround to pass data from Selenium to BeautifulSoup
                files_json = json.dumps(direct_files)
                html_content = html_content + f'<!-- SELENIUM_DIRECT_FILES: {files_json} -->'.encode('utf-8')
            
            return html_content
            
        except Exception as e:
            if verbose:
                print(f"  Error using Selenium: {e}")
            return None
    
    def _extract_files_from_selenium_dom(self, verbose: bool = False) -> List[Dict]:
        """Extract file information directly from Selenium DOM elements using same logic as BeautifulSoup"""
        files = []
        if not self.driver:
            return files
        
        try:
            # Use the same selectors as BeautifulSoup extraction
            selectors = [
                '[data-id]',
                '[data-target="file"]',
                '[data-target="folder"]',
                '[data-file-id]',
                '[data-folder-id]',
                'tr[data-id]',  # Table rows with data-id
                'div[data-id]',  # Divs with data-id
                '[role="row"][data-id]',  # Rows with role and data-id
            ]
            
            seen_ids = set()  # Track seen IDs to avoid duplicates
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        try:
                            # Get file ID using same logic as BeautifulSoup
                            file_id = (element.get_attribute('data-id') or 
                                      element.get_attribute('data-file-id') or 
                                      element.get_attribute('data-folder-id') or '')
                            
                            # Skip if no ID or already seen
                            if not file_id or file_id in seen_ids:
                                continue
                            
                            # Skip if ID is too short (likely not a valid Google Drive ID)
                            if len(file_id) < 10:
                                continue
                            
                            seen_ids.add(file_id)
                            
                            # Try to get the name from various sources (same as BeautifulSoup)
                            name = None
                            
                            # Method 1: Check data-name attribute
                            name = element.get_attribute('data-name')
                            if name:
                                name = name.strip()
                            
                            # Method 2: Check aria-label (often contains filename)
                            if not name:
                                aria_label = element.get_attribute('aria-label')
                                if aria_label:
                                    # Extract filename from aria-label (format: "Image filename.png Shared")
                                    # Remove common prefixes/suffixes
                                    name = aria_label.replace('Image', '').replace('Shared', '').strip()
                                    # Remove leading/trailing quotes if present
                                    name = name.strip('"').strip("'").strip()
                            
                            # Method 3: Look for text in child elements (table cells, divs)
                            if not name:
                                try:
                                    # Try to find text in table cells
                                    cells = element.find_elements(By.TAG_NAME, 'td')
                                    if not cells:
                                        cells = element.find_elements(By.TAG_NAME, 'div')
                                    for cell in cells:
                                        text = cell.text.strip()
                                        if text and len(text) > 2 and not text.startswith('http'):
                                            # Check if it looks like a filename
                                            if '.' in text or len(text) < 100:
                                                name = text
                                                break
                                except:
                                    pass
                            
                            # Method 4: Get text directly from element
                            if not name:
                                name = element.text.strip()
                                # Clean up - remove common prefixes
                                if name.startswith('Image'):
                                    name = name[5:].strip()
                                if name.endswith('Shared'):
                                    name = name[:-6].strip()
                            
                            # Skip if still no name or name looks invalid (same validation as BeautifulSoup)
                            if not name or len(name) < 2 or name.startswith('window.') or 'AF_initDataCallback' in name:
                                continue
                            
                            # Skip entries that look like JavaScript code or system data
                            if (name.startswith('window.') or 
                                name.startswith('AF_initDataCallback') or
                                name.startswith('%.@.') or
                                'null,null,null' in name or
                                len(name) > 1000 or  # Skip very long names (likely JS data)
                                name.count('"') > 10):  # Skip entries with too many quotes
                                continue
                            
                            # Check if this element has image previews (indicating it's a file)
                            has_image_preview = False
                            # Look for img tags within this element or its parent
                            try:
                                img_tags = element.find_elements(By.TAG_NAME, 'img')
                                if not img_tags:
                                    # Try parent element
                                    try:
                                        parent = element.find_element(By.XPATH, '..')
                                        img_tags = parent.find_elements(By.TAG_NAME, 'img')
                                    except:
                                        pass
                                if img_tags:
                                    has_image_preview = True
                            except:
                                pass
                            
                            # Get aria-label on this element or its parents
                            aria_label = element.get_attribute('aria-label')
                            if not aria_label:
                                try:
                                    parent = element.find_element(By.XPATH, '..')
                                    aria_label = parent.get_attribute('aria-label') or ''
                                except:
                                    aria_label = ''
                            
                            # Get other attributes for folder detection
                            data_target = element.get_attribute('data-target') or ''
                            class_attr = element.get_attribute('class') or ''
                            classes = class_attr.split() if class_attr else []
                            
                            # Build file item with same structure as BeautifulSoup
                            file_item = {
                                'name': name,
                                'id': file_id,
                                'mimeType': 'unknown',
                                'size': element.get_attribute('data-size') or '',
                                'isFolder': False,  # Will be set below using _is_folder
                                'class': classes,
                                'data-target': data_target,
                                'aria-label': aria_label,
                                'has_image_preview': has_image_preview
                            }
                            
                            # Use the same _is_folder method as BeautifulSoup
                            file_item['isFolder'] = self._is_folder(file_item)
                            
                            # Debug if verbose
                            self._debug_item(file_item, verbose)
                            
                            files.append(file_item)
                            
                        except Exception as e:
                            if verbose:
                                print(f"    Error extracting from element: {e}")
                            continue
                except Exception as e:
                    if verbose:
                        print(f"    Error with selector {selector}: {e}")
                    continue
            
            if verbose:
                print(f"  Extracted {len(files)} files directly from Selenium DOM")
            
        except Exception as e:
            if verbose:
                print(f"  Error extracting files from DOM: {e}")
        
        return files
    
    def cleanup_selenium(self):
        """Clean up Selenium driver if it was initialized"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def get_folder_contents_via_scraping(self, folder_id: str, verbose: bool = False, recursive: bool = False, max_depth: int = 5, current_depth: int = 0, current_path: str = "", exclude_folders: List[str] = None) -> List[Dict]:
        """Get folder contents using web scraping with optional recursive traversal"""
        if exclude_folders is None:
            exclude_folders = []
        
        if current_depth >= max_depth:
            if verbose:
                print(f"  Max depth ({max_depth}) reached, stopping recursion")
            return []
        
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        
        try:
            # Use Selenium if enabled (for scrolling to load lazy content)
            html_content = None
            if self.use_selenium:
                if verbose:
                    print(f"  Using Selenium to load folder contents...")
                html_content = self._get_page_with_selenium(url, verbose)
            
            # If Selenium didn't work or wasn't enabled, use regular requests
            if html_content is None:
                if verbose and self.use_selenium:
                    print(f"  Selenium failed, falling back to regular requests...")
                response = self.session.get(url)
                response.raise_for_status()
                html_content = response.content
            
            soup = BeautifulSoup(html_content, 'html.parser')
            files = []
            
            # Method 1: Look for file/folder data based on custom data attributes
            if not files:
                extracted_files = self._extract_data(soup)
                files.extend(extracted_files)
                if verbose and extracted_files:
                    print(f"  Found {len(extracted_files)} items via script tags")

            if not files:
                script_files = self._extract_from_script_tags(soup)
                files.extend(script_files)
                if verbose and script_files:
                    print(f"  Found {len(script_files)} items via script tags")
            
            # Method 2: Extract from HTML data attributes
            if not files:
                data_files = self._extract_from_data_attributes(soup, verbose)
                files.extend(data_files)
                if verbose and data_files:
                    print(f"  Found {len(data_files)} items via data attributes")
            
            # Method 3: Extract from HTML elements (fallback)
            if not files:
                html_files = self._scrape_file_names_from_html(soup)
                files.extend(html_files)
                if verbose and html_files:
                    print(f"  Found {len(html_files)} items via HTML scraping")
            
            # Method 4: Extract from meta tags and structured data
            if not files:
                meta_files = self._extract_from_meta_tags(soup)
                files.extend(meta_files)
                if verbose and meta_files:
                    print(f"  Found {len(meta_files)} items via meta tags")
            
            # Remove duplicates based on ID and name
            original_count = len(files)
            files = self._remove_duplicates(files)
            if verbose and original_count != len(files):
                print(f"  Removed {original_count - len(files)} duplicates")
            
            # Add path information to files
            for file_item in files:
                file_item['path'] = current_path
            
            # If recursive mode is enabled, process subfolders
            if recursive and current_depth < max_depth:
                folders = [item for item in files if item.get('isFolder', False)]
                if folders and verbose:
                    print(f"  Found {len(folders)} subfolders to process recursively")
                
                for folder in folders:
                    folder_id = folder.get('id', '')
                    folder_name = folder.get('name', 'Unknown')
                    
                    # Check if this folder should be excluded
                    if folder_name.lower() in [ex.lower() for ex in exclude_folders]:
                        if verbose:
                            print(f"  Skipping excluded folder: {folder_name}")
                        continue
                    
                    if folder_id and len(folder_id) > 10:  # Valid folder ID
                        # Create new path for subfolder
                        new_path = f"{current_path}/{folder_name}" if current_path else folder_name
                        
                        if verbose:
                            print(f"  Processing subfolder: {folder_name} (depth: {current_depth + 1})")
                        
                        try:
                            subfolder_files = self.get_folder_contents_via_scraping(
                                folder_id, 
                                verbose=verbose, 
                                recursive=recursive, 
                                max_depth=max_depth, 
                                current_depth=current_depth + 1,
                                current_path=new_path,
                                exclude_folders=exclude_folders
                            )
                            
                            # Add subfolder files to the main list
                            files.extend(subfolder_files)
                            
                            if verbose and subfolder_files:
                                print(f"    Found {len(subfolder_files)} items in subfolder: {folder_name}")
                                
                        except Exception as e:
                            if verbose:
                                print(f"    Error processing subfolder {folder_name}: {e}")
                            continue
            
            return files
            
        except requests.RequestException as e:
            print(f"Error accessing folder: {e}")
            return []

    def _extract_data(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract file/folder data from HTML elements using data-id and data-tooltip"""
        files = []
        
        # Find all elements with class i92Sbe and data-id attribute
        elements = soup.find_all(class_='i92Sbe', attrs={'data-id': True})
        
        for element in elements:
            data_id = element.get('data-id')
            data_tooltip = element.get('data-tooltip', '')
            
            # Determine if it's a folder or file based on data-tooltip
            is_folder = False
            if data_tooltip:
                tooltip_lower = data_tooltip.lower()
                if 'folder' in tooltip_lower or 'directory' in tooltip_lower:
                    is_folder = True
                elif 'file' in tooltip_lower or 'image' in tooltip_lower or 'document' in tooltip_lower:
                    is_folder = False
            
            # Get the name from element text content
            name = element.get_text(strip=True)
            
            if name and data_id:
                file_item = {
                    'name': name,
                    'id': data_id,
                    'mimeType': 'application/vnd.google-apps.folder' if is_folder else 'unknown',
                    'size': '',
                    'isFolder': is_folder,
                    'data-id': data_id
                }
                files.append(file_item)
        
        return files
        
    def _extract_from_script_tags(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract file data from JavaScript variables in script tags"""
        files = []
        script_tags = soup.find_all('script')
        
        # Look for various Google Drive data patterns
        patterns = [
            r'window\._DRIVE_ivd\s*=\s*(\[.*?\]);',
            r'window\._DRIVE_ivd\s*=\s*(\{.*?\});',
            r'AF_initDataCallback.*?data:(\[.*?\]);',
            r'AF_initDataCallback.*?data:(\{.*?\});',
            r'\["drive\.google\.com",.*?(\[.*?\])\]',
            r'\["drive\.google\.com",.*?(\{.*?\})\]'
        ]
        
        for script in script_tags:
            if script.string:
                for pattern in patterns:
                    try:
                        matches = re.findall(pattern, script.string, re.DOTALL)
                        for match in matches:
                            try:
                                data = json.loads(match)
                                files.extend(self._parse_drive_data(data))
                            except json.JSONDecodeError:
                                continue
                    except Exception:
                        continue
        
        return files
    
    def _extract_from_data_attributes(self, soup: BeautifulSoup, verbose: bool = False) -> List[Dict]:
        """Extract file data from HTML data attributes"""
        files = []
        
        # Look for elements with data attributes containing file info
        selectors = [
            '[data-id]',
            '[data-target="file"]',
            '[data-target="folder"]',
            '[data-file-id]',
            '[data-folder-id]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                file_id = (element.get('data-id') or 
                          element.get('data-file-id') or 
                          element.get('data-folder-id') or '')
                if file_id:
                    # Try to get the name from various attributes or text content
                    name = (element.get('data-name') or 
                           element.get('title') or 
                           element.get_text(strip=True) or 'Unknown')
                    # Clean up the name to extract just the filename
                    
                    # Check if this element has image previews (indicating it's a file)
                    has_image_preview = False
                    # Look for img tags within this element or its parent
                    parent_element = element.parent if element.parent else element
                    img_tags = parent_element.find_all('img') if parent_element else []
                    if img_tags:
                        has_image_preview = True
                    
                    # Look for aria-label on this element or its parents
                    aria_label = element.get('aria-label', '')
                    if not aria_label and parent_element:
                        aria_label = parent_element.get('aria-label', '')
                    
                    # Debug aria-label
                    if verbose and aria_label:
                        print(f'Found aria-label: "{aria_label}"')
                    
                    file_item = {
                        'name': name,
                        'id': file_id,
                        'mimeType': 'unknown',
                        'size': element.get('data-size', ''),
                        'isFolder': False,  # Will be set below
                        'class': element.get('class', []),
                        'data-target': element.get('data-target', ''),
                        'aria-label': aria_label,
                        'has_image_preview': has_image_preview
                    }
                    file_item['isFolder'] = self._is_folder(file_item)
                    self._debug_item(file_item, verbose)
                    files.append(file_item)
        
        return files
    
    def _extract_from_meta_tags(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract file data from meta tags and structured data"""
        files = []
        
        # Look for JSON-LD structured data
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'name' in data:
                    files.append({
                        'name': data.get('name', 'Unknown'),
                        'id': data.get('identifier', ''),
                        'mimeType': data.get('fileFormat', 'unknown'),
                        'size': data.get('contentSize', ''),
                        'isFolder': data.get('@type') == 'Folder'
                    })
            except json.JSONDecodeError:
                continue
        
        # Look for meta tags with file information
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name', '').lower()
            content = meta.get('content', '')
            
            if 'file' in name or 'folder' in name:
                # Extract ID from content if it contains a Google Drive ID pattern
                id_match = re.search(r'([a-zA-Z0-9_-]{25,})', content)
                if id_match:
                    files.append({
                        'name': content,
                        'id': id_match.group(1),
                        'mimeType': 'unknown',
                        'size': '',
                        'isFolder': 'folder' in name
                    })
        
        return files
    
    def _remove_duplicates(self, files: List[Dict]) -> List[Dict]:
        """Remove duplicate files based on ID and name, and filter out invalid entries"""
        seen_ids = set()
        seen_names = set()
        unique_files = []
        
        for file_item in files:
            name = file_item.get('name', '').strip()
            file_id = file_item.get('id', '')
            
            # Skip entries with invalid names or IDs
            if not name or len(name) < 2:
                continue
            
            # Skip entries that look like JavaScript code or system data
            if (name.startswith('window.') or 
                name.startswith('AF_initDataCallback') or
                name.startswith('%.@.') or
                'null,null,null' in name or
                len(name) > 1000 or  # Skip very long names (likely JS data)
                name.count('"') > 10):  # Skip entries with too many quotes
                continue
            
            # Skip entries with invalid IDs
            if file_id and len(file_id) < 10:
                continue
            
            # Clean the filename
            if not name:
                continue
            
            # Skip if we've already seen this ID or cleaned name
            if file_id in seen_ids or name in seen_names:
                continue
            
            # Add to seen sets
            if file_id:
                seen_ids.add(file_id)
            seen_names.add(name)
            
            # Update the file item with cleaned name
            file_item['name'] = name
            unique_files.append(file_item)
        
        return unique_files
    
    def _parse_drive_data(self, data: List) -> List[Dict]:
        """Parse Google Drive data structure"""
        files = []
        
        def extract_files_recursive(item):
            if isinstance(item, dict):
                if 'name' in item and 'id' in item:
                    file_item = {
                        'name': item.get('name', 'Unknown'),
                        'id': item.get('id', ''),
                        'mimeType': item.get('mimeType', ''),
                        'size': item.get('size', ''),
                        'isFolder': False,  # Will be set below
                        'aria-label': item.get('aria-label', ''),
                        'has_image_preview': item.get('hasThumbnail', False) or item.get('thumbnailLink', False)
                    }
                    file_item['isFolder'] = self._is_folder(file_item)
                    files.append(file_item)
                
                # Recursively search nested structures
                for value in item.values():
                    if isinstance(value, (list, dict)):
                        extract_files_recursive(value)
            elif isinstance(item, list):
                for subitem in item:
                    extract_files_recursive(subitem)
        
        extract_files_recursive(data)
        return files
    
    def _scrape_file_names_from_html(self, soup: BeautifulSoup) -> List[Dict]:
        """Enhanced fallback method to extract file names and IDs from HTML"""
        files = []
        
        # Look for file/folder names in various HTML elements with better ID extraction
        selectors = [
            '[data-target="file"]',
            '[data-target="folder"]', 
            '.a-v-T',
            '.a-v-Tb',
            '[role="gridcell"]',
            '[data-id]',
            '.a-v-Tc',  # Additional Google Drive class
            '.a-v-Td',  # Additional Google Drive class
            '[aria-label]'  # Accessibility labels often contain file names
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                # Extract name from text content or aria-label
                name = (element.get_text(strip=True) or 
                       element.get('aria-label', '') or 
                       element.get('title', '')).strip()
                
                if name and len(name) > 0:
                    # Try to extract ID from various sources
                    file_id = (element.get('data-id') or
                             element.get('data-file-id') or
                             element.get('data-folder-id') or
                             self._extract_id_from_href(element) or
                             self._extract_id_from_class(element) or
                             '')
                    
                    file_item = {
                        'name': name,
                        'id': file_id,
                        'mimeType': 'unknown',
                        'size': element.get('data-size', ''),
                        'isFolder': False,  # Will be set below
                        'class': element.get('class', []),
                        'data-target': element.get('data-target', ''),
                        'aria-label': element.get('aria-label', '')
                    }
                    file_item['isFolder'] = self._is_folder(file_item)
                    files.append(file_item)
        
        # Also look for links that might contain file IDs
        files.extend(self._extract_from_links(soup))
        
        return files
    
    def _extract_id_from_href(self, element) -> str:
        """Extract Google Drive ID from href attribute"""
        href = element.get('href', '')
        if href:
            # Look for Google Drive ID patterns in href
            patterns = [
                r'/file/d/([a-zA-Z0-9_-]+)',
                r'/folders/([a-zA-Z0-9_-]+)',
                r'id=([a-zA-Z0-9_-]+)',
                r'/([a-zA-Z0-9_-]{25,})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, href)
                if match:
                    return match.group(1)
        
        return ''
    
    def _extract_id_from_class(self, element) -> str:
        """Extract Google Drive ID from class names"""
        classes = element.get('class', [])
        for class_name in classes:
            # Google Drive sometimes embeds IDs in class names
            id_match = re.search(r'([a-zA-Z0-9_-]{25,})', class_name)
            if id_match:
                return id_match.group(1)
        return ''
    
    def _extract_from_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract file information from links"""
        files = []
        
        # Look for links that point to Google Drive files/folders
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            if 'drive.google.com' in href:
                file_id = self.extract_file_id(href)
                if file_id:
                    name = (link.get_text(strip=True) or 
                           link.get('title', '') or 
                           link.get('aria-label', '')).strip()
                    
                    if name:
                        # Check if this link has image previews (indicating it's a file)
                        has_image_preview = False
                        img_tags = link.find_all('img')
                        if img_tags:
                            has_image_preview = True
                        
                        file_item = {
                            'name': name,
                            'id': file_id,
                            'mimeType': 'unknown',
                            'size': '',
                            'isFolder': False,  # Will be set below
                            'href': href,
                            'aria-label': link.get('aria-label', ''),
                            'has_image_preview': has_image_preview
                        }
                        file_item['isFolder'] = self._is_folder(file_item)
                        files.append(file_item)
        
        return files
    
    def get_file_info_via_scraping(self, file_id: str) -> Optional[Dict]:
        """Get file information using web scraping"""
        url = f"https://drive.google.com/file/d/{file_id}/view"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract file name from title or other elements
            title = soup.find('title')
            name = title.get_text().strip() if title else 'Unknown'
            
            # Remove "Google Drive" suffix if present
            if ' - Google Drive' in name:
                name = name.replace(' - Google Drive', '')
            
            return {
                'id': file_id,
                'name': name,
                'mimeType': 'unknown',
                'size': '',
                'isFolder': False
            }
            
        except requests.RequestException as e:
            print(f"Error accessing file: {e}")
            return None
    
    def format_file_size(self, size_bytes: Optional[str]) -> str:
        """Format file size in human readable format"""
        if not size_bytes:
            return "Unknown"
        
        try:
            size = int(size_bytes)
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} PB"
        except (ValueError, TypeError):
            return "Unknown"
    
    def generate_mpcfill_xml(self, files: List[Dict], output_file: str, quantity: int = None, bracket: int = None, stock: str = "(S30) Standard Smooth", foil: bool = False, double_sided_pairs: List[tuple] = None, cardback: str = "12RJeMQw2E0jEz4SwKJTItoONCeHD7skj", card_multiples: Dict[str, int] = None, exclude_names: List[str] = None) -> None:
        """Generate MPCFill XML from the file data in memory"""
        
        if exclude_names is None:
            exclude_names = []
        
        # Filter out folders and only keep files
        file_items = [item for item in files if not item.get('isFolder', False)]
        
        # Filter out excluded files based on filename
        if exclude_names:
            original_count = len(file_items)
            file_items = [item for item in file_items if item.get('name', '').lower() not in [ex.lower() for ex in exclude_names]]
            excluded_count = original_count - len(file_items)
            if excluded_count > 0:
                print(f"Excluded {excluded_count} file(s) based on filename")
        
        if not file_items:
            print("No files found to generate XML")
            return
        
        # Handle double-sided cards and card multiples
        front_cards = []
        back_cards = []
        
        if double_sided_pairs:
            # Create a mapping of filename to file item for quick lookup
            file_map = {item.get('name', ''): item for item in file_items}
            
            # Track which files are used in double-sided pairs
            used_file_names = set()
            
            for front_name, back_name in double_sided_pairs:
                front_item = file_map.get(front_name)
                back_item = file_map.get(back_name)
                
                if front_item and back_item:
                    # Apply multiples to double-sided pairs
                    front_multiple = card_multiples.get(front_name, 1) if card_multiples else 1
                    back_multiple = card_multiples.get(back_name, 1) if card_multiples else 1
                    
                    # Add multiple copies of front and back cards
                    for _ in range(front_multiple):
                        front_cards.append(front_item)
                    for _ in range(back_multiple):
                        back_cards.append(back_item)
                    
                    used_file_names.add(front_name)
                    used_file_names.add(back_name)
                    print(f"Added double-sided pair: {front_name} (x{front_multiple}) -> {back_name} (x{back_multiple})")
                else:
                    missing = []
                    if not front_item:
                        missing.append(front_name)
                    if not back_item:
                        missing.append(back_name)
                    print(f"Warning: Could not find files for double-sided pair: {missing}")
            
            # Add remaining files as single-sided front cards with multiples
            for item in file_items:
                item_name = item.get('name', '')
                if item_name not in used_file_names:
                    multiple = card_multiples.get(item_name, 1) if card_multiples else 1
                    for _ in range(multiple):
                        front_cards.append(item)
                    if multiple > 1:
                        print(f"Added {multiple} copies of: {item_name}")
        else:
            # All files are front cards with multiples
            for item in file_items:
                item_name = item.get('name', '')
                multiple = card_multiples.get(item_name, 1) if card_multiples else 1
                for _ in range(multiple):
                    front_cards.append(item)
                if multiple > 1:
                    print(f"Added {multiple} copies of: {item_name}")
        
        # Auto-calculate quantity and bracket if not specified
        card_count = len(front_cards)
        if quantity is None:
            quantity = card_count
        if bracket is None:
            # Use MPC bracket sizes from CSV
            bracket = self._find_next_bracket(card_count)
        
        # Create root element
        order = Element('order')
        
        # Add details
        details = SubElement(order, 'details')
        SubElement(details, 'quantity').text = str(quantity)
        SubElement(details, 'bracket').text = str(bracket)
        SubElement(details, 'stock').text = stock
        SubElement(details, 'foil').text = str(foil).lower()
        
        # Add fronts section
        fronts = SubElement(order, 'fronts')
        
        # Add each front card
        for i, file_item in enumerate(front_cards):
            card = SubElement(fronts, 'card')
            SubElement(card, 'id').text = file_item.get('id', '')
            SubElement(card, 'slots').text = str(i)
            SubElement(card, 'name').text = file_item.get('name', 'Unknown')
        
        # Add backs section only if we have back cards
        if back_cards:
            backs = SubElement(order, 'backs')
            
            # Add each back card
            for i, file_item in enumerate(back_cards):
                card = SubElement(backs, 'card')
                SubElement(card, 'id').text = file_item.get('id', '')
                SubElement(card, 'slots').text = str(i)
                SubElement(card, 'name').text = file_item.get('name', 'Unknown')
                # Add query field based on filename (remove extension and clean up)
                query_name = file_item.get('name', 'Unknown').replace('.png', '').replace('.jpg', '').replace('.jpeg', '').lower()
                SubElement(card, 'query').text = query_name
        
        # Add cardback (using provided ID or default)
        SubElement(order, 'cardback').text = cardback
        
        # Convert to pretty-printed XML
        rough_string = tostring(order, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")
        
        # Create outputs directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(f"Created directory: {output_dir}")
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        print(f"\nMPCFill XML generated successfully!")
        print(f"Output file: {output_file}")
        print(f"Generated {len(front_cards)} front cards")
        if back_cards:
            print(f"Generated {len(back_cards)} back cards")
        print(f"Quantity: {quantity} cards")
        print(f"Bracket: {bracket} cards")
        print(f"XML format matches MPCFill requirements")
    
    def process_drive_link(self, url: str, verbose: bool = False, recursive: bool = False, max_depth: int = 5, exclude_folders: List[str] = None, xml_output: str = None, xml_stock: str = "(S30) Standard Smooth", xml_foil: bool = False, double_sided_pairs: List[tuple] = None, xml_cardback: str = "12RJeMQw2E0jEz4SwKJTItoONCeHD7skj", card_multiples: Dict[str, int] = None):
        """Main method to process a Google Drive link"""
        print(f"Processing Google Drive link: {url}")
        print("-" * 50)
        
        file_id = self.extract_file_id(url)
        if not file_id:
            print("Error: Could not extract file/folder ID from the URL")
            print("Please make sure the URL is a valid Google Drive link")
            return
        
        print(f"Extracted ID: {file_id}")
        
        # Determine if it's a folder or file based on URL pattern
        is_folder = '/folders/' in url or '/drive/folders/' in url
        
        if is_folder:
            print("Detected: Folder")
            print("\nFolder Contents:")
            print("-" * 30)
            
            contents = self.get_folder_contents_via_scraping(file_id, verbose, recursive, max_depth, exclude_folders=exclude_folders)
            
            if not contents:
                print("No files found or unable to access folder contents")
                print("This might be due to:")
                print("- Private folder (requires authentication)")
                print("- Network connectivity issues")
                print("- Google Drive structure changes")
                return
            
            # Sort contents: folders first, then files
            folders = [item for item in contents if item.get('isFolder', False)]
            files = [item for item in contents if not item.get('isFolder', False)]
            
            # Display folders
            if folders:
                print(f"\nFolders ({len(folders)}):")
                for folder in folders:
                    folder_id = folder.get('id', '')
                    folder_name = folder.get('name', 'Unknown')
                    folder_path = folder.get('path', '')  # Add path info if available
                    
                    if folder_id:
                        if folder_path:
                            print(f"  [FOLDER] {folder_name} (ID: {folder_id}) [{folder_path}]")
                        else:
                            print(f"  [FOLDER] {folder_name} (ID: {folder_id})")
                    else:
                        print(f"  [FOLDER] {folder_name}")
            
            # Filter out excluded files based on filename
            if exclude_folders:
                original_file_count = len(files)
                files = [item for item in files if item.get('name', '').lower() not in [ex.lower() for ex in exclude_folders]]
                excluded_file_count = original_file_count - len(files)
                if excluded_file_count > 0:
                    print(f"\nExcluded {excluded_file_count} file(s) based on filename")
            
            # Display files
            if files:
                print(f"\nFiles ({len(files)}):")
                for file_item in files:
                    size = self.format_file_size(file_item.get('size'))
                    file_id = file_item.get('id', '')
                    file_name = file_item.get('name', 'Unknown')
                    file_path = file_item.get('path', '')  # Add path info if available
                    
                    if file_id:
                        if file_path:
                            print(f"  [FILE] {file_name} ({size}) (ID: {file_id}) [{file_path}]")
                        else:
                            print(f"  [FILE] {file_name} ({size}) (ID: {file_id})")
                    else:
                        print(f"  [FILE] {file_name} ({size})")
            
            print(f"\nTotal: {len(folders)} folders, {len(files)} files")
            if recursive:
                print(f"Recursive mode: Processed up to depth {max_depth}")
            
            # Generate XML if requested
            if xml_output:
                self.generate_mpcfill_xml(contents, xml_output, None, None, xml_stock, xml_foil, double_sided_pairs, xml_cardback, card_multiples, exclude_folders)
        
        else:
            print("Detected: File")
            file_info = self.get_file_info_via_scraping(file_id)
            
            if file_info:
                print(f"Name: {file_info.get('name', 'Unknown')}")
                print(f"ID: {file_id}")
                size = self.format_file_size(file_info.get('size'))
                print(f"Size: {size}")
            else:
                print("Unable to retrieve file information")
                print(f"File ID: {file_id}")

def main():
    parser = argparse.ArgumentParser(
        description='List files and directories from a Google Drive link',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python google_drive_lister.py "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --recursive "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --recursive --max-depth 3 "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --verbose --recursive "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --recursive --exclude "temp,backup,old,unwanted.png" "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --output cards.xml "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --recursive --output cards.xml "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --output cards.xml --double-sided "front1.png|back1.png;front2.png|back2.png" "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --output cards.xml --card-multiples "card1.png|3;card2.png|2;card3.png|4" "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --output cards.xml --card-multiples "card1.png|3;frontCard.png|backCard.png;card2.png|2" "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --output cards.xml --double-sided "front1.png|back1.png" --card-multiples "front1.png|2;back1.png|2" "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py --use-raw-html "https://drive.google.com/drive/folders/1ABC123..."
  python google_drive_lister.py "https://drive.google.com/file/d/1XYZ789..."
  python google_drive_lister.py "https://drive.google.com/open?id=1DEF456..."
  
Note: This script works with public Google Drive links. For private folders,
you may need to use the authenticated version with Google Drive API.

Selenium is used by default to scroll and load all lazy-loaded content. This requires
installing selenium and a browser driver. Use --use-raw-html for faster raw HTML scraping
(but may miss files that require scrolling to load).
        """
    )
    
    parser.add_argument(
        'url',
        help='Google Drive URL to process'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Recursively process subfolders'
    )
    
    parser.add_argument(
        '--max-depth',
        type=int,
        default=5,
        help='Maximum recursion depth (default: 5)'
    )
    
    parser.add_argument(
        '--exclude',
        type=str,
        default='',
        help='Comma-separated list of folder and file names to exclude from processing (case-insensitive)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Generate MPCFill XML file with the specified filename (defaults to outputs/ directory)'
    )
    
    parser.add_argument(
        '--stock',
        type=str,
        default='(S30) Standard Smooth',
        help='Card stock type for MPCFill XML file (default: "(S30) Standard Smooth")'
    )
    
    parser.add_argument(
        '--foil',
        action='store_true',
        help='Enable foil cards in MPCFill XML file (default: false)'
    )
    
    parser.add_argument(
        '--double-sided',
        type=str,
        help='Semicolon-separated pairs of front|back filenames for double-sided cards (e.g., "front1.png|back1.png;front2.png|back2.png")'
    )
    
    parser.add_argument(
        '--cardback',
        type=str,
        default='12RJeMQw2E0jEz4SwKJTItoONCeHD7skj',
        help='The Google Drive ID of the cardback image for MPCFill XML file (default: "12RJeMQw2E0jEz4SwKJTItoONCeHD7skj")'
    )
    
    parser.add_argument(
        '--card-multiples',
        type=str,
        help='Semicolon-separated list of filename|count or frontCard|backCard pairs for multiple copies (e.g., "card1.png|3;frontCard.png|backCard.png;card2.png|2")'
    )
    
    parser.add_argument(
        '--use-raw-html',
        action='store_true',
        help='Use raw HTML scraping instead of Selenium (faster but may miss lazy-loaded content). Selenium is used by default to scroll and load all files.'
    )
    
    args = parser.parse_args()
    
    # Parse exclude folders
    exclude_folders = []
    if args.exclude:
        exclude_folders = [folder.strip() for folder in args.exclude.split(',') if folder.strip()]
    
    # Parse double-sided pairs
    double_sided_pairs = []
    if args.double_sided:
        # Split by semicolon to get pairs
        pairs = [pair.strip() for pair in args.double_sided.split(';') if pair.strip()]
        
        for pair in pairs:
            if '|' not in pair:
                print(f"Error: Invalid double-sided format: {pair}. Expected 'front|back'")
                return
            
            front_name, back_name = pair.split('|', 1)
            front_name = front_name.strip()
            back_name = back_name.strip()
            
            if not front_name or not back_name:
                print(f"Error: Empty front or back name in pair: {pair}")
                return
            
            double_sided_pairs.append((front_name, back_name))
            print(f"Added double-sided pair: {front_name} -> {back_name}")
    
    # Parse card multiples
    card_multiples = {}
    if args.card_multiples:
        # Split by semicolon to get pairs
        pairs = [pair.strip() for pair in args.card_multiples.split(';') if pair.strip()]
        
        for pair in pairs:
            if '|' not in pair:
                print(f"Error: Invalid card multiples format: {pair}. Expected 'filename|count' or 'frontCard|backCard'")
                return
            
            parts = pair.split('|')
            if len(parts) == 2:
                # Check if second part is a number (filename|count) or another filename (frontCard|backCard)
                second_part = parts[1].strip()
                try:
                    # Try to parse as number
                    count = int(second_part)
                    if count < 1:
                        print(f"Error: Count must be at least 1 for {parts[0]}")
                        return
                    card_multiples[parts[0].strip()] = count
                    print(f"Added {count} copies of: {parts[0].strip()}")
                except ValueError:
                    # Not a number, treat as front|back pair
                    front_card = parts[0].strip()
                    back_card = second_part
                    card_multiples[front_card] = 1
                    card_multiples[back_card] = 1
                    print(f"Added front|back pair: {front_card} | {back_card}")
            else:
                print(f"Error: Invalid card multiples format: {pair}. Expected 'filename|count' or 'frontCard|backCard'")
                return
    
    # Validate URL
    if not args.url.startswith(('http://', 'https://')):
        print("Error: Please provide a valid URL")
        sys.exit(1)
    
    # Determine if we should use Selenium (default) or raw HTML
    use_selenium = not args.use_raw_html
    
    # Check if Selenium is needed but not available
    if use_selenium and not SELENIUM_AVAILABLE:
        print("Warning: Selenium is required (default) but is not installed.")
        print("Install it with: pip install selenium")
        print("You also need to install a browser driver (ChromeDriver or GeckoDriver)")
        print("Falling back to raw HTML scraping...")
        use_selenium = False
    
    # Create lister instance and process the link
    lister = GoogleDriveLister(use_selenium=use_selenium)
    
    try:
        # Modify xml_output to use outputs directory by default
        xml_output = args.output
        if xml_output and not os.path.dirname(xml_output):
            xml_output = os.path.join('outputs', xml_output)
        
        lister.process_drive_link(
            args.url, 
            args.verbose, 
            args.recursive, 
            args.max_depth, 
            exclude_folders,
            xml_output,
            args.stock,
            args.foil,
            double_sided_pairs,
            args.cardback,
            card_multiples
        )
    finally:
        # Clean up Selenium driver if it was used
        lister.cleanup_selenium()

if __name__ == "__main__":
    main()
