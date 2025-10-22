import re

def is_valid_phone(phone: str) -> bool:
    """
    A simple phone number validator for Ukrainian numbers.
    Checks for a plausible length after cleaning non-digit characters.
    """
    # Remove all non-digit characters
    cleaned_phone = re.sub(r'\D', '', phone)
    # Allows for formats like 0991234567 (10 digits) or 380991234567 (12 digits)
    return 10 <= len(cleaned_phone) <= 12