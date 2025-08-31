from urllib.parse import urlencode

def add_query_params_to_url(base_url, params):
    """
    Append query parameters to a base URL without parsing the URL first.

    - Skips parameters with value None.
    - Values are converted to strings and URL-encoded.
    - Preserves existing query separators on the base_url.

    Parameters
    - base_url: the URL string to append params to
    - params: mapping of keys to values (values of None are skipped)

    Returns
    - A new URL string with encoded query parameters appended.
    """
    if not params:
        return base_url

    cleaned_params = {}
    for name, value in params.items():
        if value is None:
            continue
        cleaned_params[str(name)] = str(value)

    if not cleaned_params:
        return base_url

    encoded_query = urlencode(cleaned_params, doseq=True)

    if base_url.endswith('?') or base_url.endswith('&'):
        separator = ''
    elif '?' in base_url:
        separator = '&'
    else:
        separator = '?'

    result = f"{base_url}{separator}{encoded_query}"
    return result


