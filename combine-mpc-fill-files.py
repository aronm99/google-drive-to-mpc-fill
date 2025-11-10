#!/usr/bin/env python3
"""
Combine Multiple MPC Fill XML Files

This script combines multiple MPC fill XML files into a single XML file.
It merges all front cards, back cards, and recalculates quantities and brackets.

Usage:
    python combine-mpc-fill-files.py file1.xml file2.xml file3.xml -o combined.xml
    python combine-mpc-fill-files.py *.xml -o combined.xml
    python combine-mpc-fill-files.py outputs/*.xml -o outputs/combined.xml
"""

import argparse
import sys
import os
from xml.etree.ElementTree import Element, SubElement, parse, tostring
from xml.dom import minidom
from typing import List, Tuple

DEFAULT_BRACKET_SIZE = [18, 36, 55, 72, 90, 108, 126, 144, 162, 180, 198, 216, 234, 396, 504, 612]


def find_next_bracket(quantity: int) -> int:
    """Find the next largest bracket size for the given quantity"""
    for bracket in DEFAULT_BRACKET_SIZE:
        if bracket >= quantity:
            return bracket
    
    # If quantity exceeds all brackets, return the largest one
    return DEFAULT_BRACKET_SIZE[-1] if DEFAULT_BRACKET_SIZE else quantity


def parse_xml_file(file_path: str) -> Tuple[dict, List[dict], List[dict], str]:
    """
    Parse an MPC fill XML file and extract its components.
    
    Returns:
        tuple: (details_dict, front_cards, back_cards, cardback_id)
    """
    try:
        tree = parse(file_path)
        root = tree.getroot()
        
        # Extract details
        details = root.find('details')
        details_dict = {}
        if details is not None:
            quantity_elem = details.find('quantity')
            bracket_elem = details.find('bracket')
            stock_elem = details.find('stock')
            foil_elem = details.find('foil')
            
            details_dict = {
                'quantity': int(quantity_elem.text) if quantity_elem is not None and quantity_elem.text else None,
                'bracket': int(bracket_elem.text) if bracket_elem is not None and bracket_elem.text else None,
                'stock': stock_elem.text if stock_elem is not None else '(S30) Standard Smooth',
                'foil': foil_elem.text.lower() == 'true' if foil_elem is not None and foil_elem.text else False
            }
        
        # Extract front cards
        fronts = root.find('fronts')
        front_cards = []
        if fronts is not None:
            for card in fronts.findall('card'):
                card_data = {
                    'id': card.find('id').text if card.find('id') is not None else '',
                    'slots': card.find('slots').text if card.find('slots') is not None else '',
                    'name': card.find('name').text if card.find('name') is not None else ''
                }
                front_cards.append(card_data)
        
        # Extract back cards
        backs = root.find('backs')
        back_cards = []
        if backs is not None:
            for card in backs.findall('card'):
                card_data = {
                    'id': card.find('id').text if card.find('id') is not None else '',
                    'slots': card.find('slots').text if card.find('slots') is not None else '',
                    'name': card.find('name').text if card.find('name') is not None else '',
                    'query': card.find('query').text if card.find('query') is not None else ''
                }
                back_cards.append(card_data)
        
        # Extract cardback
        cardback_elem = root.find('cardback')
        cardback_id = cardback_elem.text if cardback_elem is not None and cardback_elem.text else '12RJeMQw2E0jEz4SwKJTItoONCeHD7skj'
        
        return details_dict, front_cards, back_cards, cardback_id
        
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        raise


def combine_xml_files(input_files: List[str], output_file: str, 
                     stock: str = None, foil: bool = None, 
                     cardback: str = None, auto_bracket: bool = True) -> None:
    """
    Combine multiple MPC fill XML files into a single file.
    
    Args:
        input_files: List of input XML file paths
        output_file: Output XML file path
        stock: Override stock type (uses first file's stock if None)
        foil: Override foil setting (uses first file's foil if None)
        cardback: Override cardback ID (uses first file's cardback if None)
        auto_bracket: If True, automatically calculate bracket based on total quantity
    """
    if not input_files:
        print("Error: No input files specified", file=sys.stderr)
        sys.exit(1)
    
    all_front_cards = []
    all_back_cards = []
    all_details = []
    cardback_ids = []
    
    print(f"Reading {len(input_files)} XML file(s)...")
    
    # Parse all input files
    for i, file_path in enumerate(input_files):
        # Check if file exists, if not try outputs/ directory if no directory specified
        resolved_path = file_path
        if not os.path.exists(file_path):
            # If no directory specified, try outputs/ directory
            if not os.path.dirname(file_path):
                outputs_path = os.path.join('outputs', file_path)
                if os.path.exists(outputs_path):
                    resolved_path = outputs_path
                else:
                    print(f"Warning: File not found: {file_path} or {outputs_path}", file=sys.stderr)
                    continue
            else:
                print(f"Warning: File not found: {file_path}", file=sys.stderr)
                continue
        
        print(f"  [{i+1}/{len(input_files)}] Parsing {resolved_path}...")
        try:
            details, front_cards, back_cards, cardback_id = parse_xml_file(resolved_path)
            
            all_details.append(details)
            all_front_cards.extend(front_cards)
            all_back_cards.extend(back_cards)
            cardback_ids.append(cardback_id)
            
            print(f"    - {len(front_cards)} front card(s), {len(back_cards)} back card(s)")
            
        except Exception as e:
            print(f"    Error: {e}", file=sys.stderr)
            continue
    
    if not all_front_cards and not all_back_cards:
        print("Error: No cards found in any input files", file=sys.stderr)
        sys.exit(1)
    
    # Determine combined details
    total_front_cards = len(all_front_cards)
    total_back_cards = len(all_back_cards)
    
    # Use first file's details as base, or provided overrides
    base_details = all_details[0] if all_details else {}
    
    # Calculate quantity (use total front cards if not specified)
    if total_back_cards > 0:
        # For double-sided cards, quantity should match the number of card pairs
        quantity = max(total_front_cards, total_back_cards)
    else:
        quantity = total_front_cards
    
    # Determine bracket
    if auto_bracket:
        bracket = find_next_bracket(quantity)
    else:
        # Use the maximum bracket from all files
        brackets = [d.get('bracket', 0) for d in all_details if d.get('bracket')]
        bracket = max(brackets) if brackets else find_next_bracket(quantity)
    
    # Determine stock (use override, first file's stock, or default)
    final_stock = stock if stock is not None else (base_details.get('stock') or '(S30) Standard Smooth')
    
    # Determine foil (use override, first file's foil, or default)
    if foil is not None:
        final_foil = foil
    else:
        final_foil = base_details.get('foil', False)
    
    # Determine cardback (use override, first file's cardback, or default)
    final_cardback = cardback if cardback is not None else (cardback_ids[0] if cardback_ids else '12RJeMQw2E0jEz4SwKJTItoONCeHD7skj')
    
    # Create combined XML structure
    order = Element('order')
    
    # Add details
    details_elem = SubElement(order, 'details')
    SubElement(details_elem, 'quantity').text = str(quantity)
    SubElement(details_elem, 'bracket').text = str(bracket)
    SubElement(details_elem, 'stock').text = final_stock
    SubElement(details_elem, 'foil').text = str(final_foil).lower()
    
    # Add front cards with renumbered slots
    fronts_elem = SubElement(order, 'fronts')
    for i, card in enumerate(all_front_cards):
        card_elem = SubElement(fronts_elem, 'card')
        SubElement(card_elem, 'id').text = card['id']
        SubElement(card_elem, 'slots').text = str(i)
        SubElement(card_elem, 'name').text = card['name']
    
    # Add back cards with renumbered slots (if any)
    if all_back_cards:
        backs_elem = SubElement(order, 'backs')
        for i, card in enumerate(all_back_cards):
            card_elem = SubElement(backs_elem, 'card')
            SubElement(card_elem, 'id').text = card['id']
            SubElement(card_elem, 'slots').text = str(i)
            SubElement(card_elem, 'name').text = card['name']
            if card.get('query'):
                SubElement(card_elem, 'query').text = card['query']
    
    # Add cardback
    SubElement(order, 'cardback').text = final_cardback
    
    # Convert to pretty-printed XML
    rough_string = tostring(order, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ")
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created directory: {output_dir}")
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    # Print summary
    print(f"\n✓ Combined XML file created successfully!")
    print(f"  Output file: {output_file}")
    print(f"  Total front cards: {total_front_cards}")
    if total_back_cards > 0:
        print(f"  Total back cards: {total_back_cards}")
    print(f"  Quantity: {quantity}")
    print(f"  Bracket: {bracket}")
    print(f"  Stock: {final_stock}")
    print(f"  Foil: {final_foil}")
    print(f"  Cardback ID: {final_cardback}")


def main():
    parser = argparse.ArgumentParser(
        description='Combine multiple MPC fill XML files into a single file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml
  python combine-mpc-fill-files.py outputs/*.xml -o combined.xml
  python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --stock "(S33) Superior Smooth"
  python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --foil
  python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --cardback "YOUR_CARDBACK_ID"
  python combine-mpc-fill-files.py file1.xml file2.xml -o combined.xml --no-auto-bracket

Note: 
  - If no directory is specified in the input file paths, the script will look in the outputs/ directory by default
  - If no directory is specified in the output path, files will be saved to the outputs/ directory by default
        """
    )
    
    parser.add_argument(
        'input_files',
        nargs='+',
        help='Input XML files to combine (defaults to outputs/ directory if no directory specified)'
    )
    
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output XML file path (defaults to outputs/ directory if no directory specified)'
    )
    
    parser.add_argument(
        '--stock',
        type=str,
        help='Override stock type (e.g., "(S30) Standard Smooth", "(S33) Superior Smooth")'
    )
    
    parser.add_argument(
        '--foil',
        action='store_true',
        help='Enable foil cards (overrides input files)'
    )
    
    parser.add_argument(
        '--no-foil',
        action='store_true',
        help='Disable foil cards (overrides input files)'
    )
    
    parser.add_argument(
        '--cardback',
        type=str,
        help='Override cardback Google Drive ID'
    )
    
    parser.add_argument(
        '--no-auto-bracket',
        action='store_true',
        help='Disable automatic bracket calculation (uses maximum bracket from input files)'
    )
    
    args = parser.parse_args()
    
    # Determine foil setting
    foil = None
    if args.foil:
        foil = True
    elif args.no_foil:
        foil = False
    
    # Default output to outputs/ directory if no directory specified
    output_file = args.output
    if not os.path.dirname(output_file):
        output_file = os.path.join('outputs', output_file)
    
    # Combine files
    combine_xml_files(
        args.input_files,
        output_file,
        stock=args.stock,
        foil=foil,
        cardback=args.cardback,
        auto_bracket=not args.no_auto_bracket
    )


if __name__ == "__main__":
    main()

