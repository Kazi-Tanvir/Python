"""
Basic Phone Information Module
==============================
Parses and validates phone numbers using the `phonenumbers` library.
Extracts carrier, geocoding, timezone, line type, and formatting info.
"""

import phonenumbers
from phonenumbers import (
    geocoder,
    carrier as pn_carrier,
    timezone as pn_timezone,
    phonenumberutil,
)

from osint.report import ModuleResult


# Map PhoneNumberType enum to human-readable strings
_LINE_TYPES = {
    phonenumberutil.PhoneNumberType.FIXED_LINE: "Fixed Line (Landline)",
    phonenumberutil.PhoneNumberType.MOBILE: "Mobile",
    phonenumberutil.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed Line or Mobile",
    phonenumberutil.PhoneNumberType.TOLL_FREE: "Toll-Free",
    phonenumberutil.PhoneNumberType.PREMIUM_RATE: "Premium Rate",
    phonenumberutil.PhoneNumberType.SHARED_COST: "Shared Cost",
    phonenumberutil.PhoneNumberType.VOIP: "VoIP",
    phonenumberutil.PhoneNumberType.PERSONAL_NUMBER: "Personal Number",
    phonenumberutil.PhoneNumberType.PAGER: "Pager",
    phonenumberutil.PhoneNumberType.UAN: "UAN (Universal Access)",
    phonenumberutil.PhoneNumberType.VOICEMAIL: "Voicemail",
    phonenumberutil.PhoneNumberType.UNKNOWN: "Unknown",
}


def lookup(phone_raw: str, parsed: phonenumbers.PhoneNumber) -> ModuleResult:
    """
    Extract all basic info from a parsed phone number.

    Args:
        phone_raw: The raw phone number string as entered.
        parsed: Pre-parsed PhoneNumber object.

    Returns:
        ModuleResult with carrier, location, timezone, formatting, etc.
    """
    result = ModuleResult(module_name="basic_info")

    try:
        # Validation
        is_valid = phonenumbers.is_valid_number(parsed)
        is_possible = phonenumbers.is_possible_number(parsed)

        # Formatting variants
        e164 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        international = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        national = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )
        rfc3966 = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.RFC3966
        )

        # Geocoding (location)
        location = geocoder.description_for_number(parsed, "en") or "Unknown"

        # Carrier
        carrier_name = pn_carrier.name_for_number(parsed, "en") or "Unknown"

        # Timezone
        tz_list = list(pn_timezone.time_zones_for_number(parsed))

        # Line type
        number_type = phonenumbers.number_type(parsed)
        line_type = _LINE_TYPES.get(number_type, "Unknown")

        # Country info
        country_code = parsed.country_code
        region_code = phonenumbers.region_code_for_number(parsed)
        country_name = geocoder.country_name_for_number(parsed, "en") or "Unknown"

        result.data = {
            "Valid Number": "✅ Yes" if is_valid else "❌ No",
            "Possible Number": "✅ Yes" if is_possible else "❌ No",
            "Country": f"{country_name} ({region_code})",
            "Country Code": f"+{country_code}",
            "Location": location,
            "Carrier / Network": carrier_name,
            "Line Type": line_type,
            "Timezone(s)": ", ".join(tz_list) if tz_list else "Unknown",
            "E.164 Format": e164,
            "International": international,
            "National": national,
            "RFC3966 (tel:)": rfc3966,
        }

        result.success = True

    except Exception as e:
        result.errors.append(f"Basic info extraction failed: {e}")

    return result
