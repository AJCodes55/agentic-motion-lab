"""Explicit analytical scope limits, independent of model classification."""
import re
import unicodedata
from calendar import month_name


_MONTH_NAMES = (r'\b(?:january|february|march|april|may|june|july|august|'
                r'september|october|november|december|\d{4}-\d{2})\b')


def _unsupported_reason(command: str) -> str | None:
    """Reject unsupported analyses before a model can reinterpret them as a supported metric."""
    command = unicodedata.normalize('NFKC', command).casefold()
    command = re.sub(r'[‐‑‒–—−]', '-', command)
    if re.search(
        r'\b(forecast\w*|predict\w*|why|caus\w*|revenue|profit|weather|'
        r'correlat\w*|quarter\w*|annual|yearly|median|distance|speed)\b', command):
        return 'This request is outside the supported monthly analytical scope.'
    if len(set(re.findall(_MONTH_NAMES, command))) > 2:
        return 'Only one reporting month and its immediately preceding month are supported.'
    guards = (
        (r'\b(?:weeks?|weekly|hours?|hourly|weekdays?|weekends?)\b',
         'Weekly, hourly and weekday/weekend grouping are not supported.'),
        (r'\b(?:routes?|origin\s*-?\s*destination|origin\s+(?:and|to)\s+destination)\b',
         'Origin-destination route analysis is not supported; station starts and ends are separate metrics.'),
        (r'\b(?:riders?|users?|people|individuals?)\b.*\b(?:identit\w*|histories|history|names?|personal)\b',
         'Individual rider identities and travel histories are not supported.'),
        (r'\b(?:sql|python|javascript|shell|execute code|run code)\b',
         'Arbitrary SQL and code execution are not supported.'),
        (r'\b(?:invent\w*|fabricat\w*|make up|ignore validation|bypass validation)\b',
         'Only verified dataset values can be reported; inventing data or bypassing validation is not supported.'),
        (r'\b(?:rank\w*|top|bottom|highest|lowest|largest|biggest)\b.*\bby\s+'
         r'(?:(?:their|the|absolute|percentage|percent|trip|count|month[- ]over[- ]month)\s+)*'
         r'(?:growth|changes?|increases?|decreases?|declines?)\b'
         r'|\b(?:highest|lowest|largest|biggest|most|least)\s+(?:growth|increase|decrease|decline|change)\b',
         'Ranking by growth or change is not supported. Use a standard report for station movers.'),
        (r'\bcompar\w*\b.*\b(?:every|each|all)\s+'
         r'(?:(?:one|of|the|returned|ranked|top|bottom|\d+)\s+)*stations?\b'
         r'|\b(?:top|bottom)\s+\d+\b.*\bcompar\w*\b.*\b(?:each|every|all)\b',
         'Comparing every ranked station is not supported. Select one explicit station for comparison.'),
    )
    for pattern, reason in guards:
        if re.search(pattern, command):
            return reason
    if re.search(r'\b(?:rank\w*|leaderboard|top|bottom|highest|lowest|most|least)\b', command):
        if re.search(r'\bmember(?:[- ]rider)?\s+share\b|\bclassic(?:[- ]bike)?\s+share\b', command):
            return 'Station share rankings support e-bike share or casual-rider share only.'
        limit = re.search(r'\b(?:top|bottom)\s+(\d+)\b', command)
        if limit and not 1 <= int(limit.group(1)) <= 10:
            return 'Station rankings support a limit of 1 to 10.'
    return None


def _unsupported_command(command: str) -> bool:
    return _unsupported_reason(command) is not None


def _station_count_comparison(command: str, year: int, month: int) -> dict | None:
    """Resolve explicit ID/count comparisons without a model; preserve the selected month boundary."""
    # shortcut: explicit ID/count phrases only; extend when another real wording needs offline routing.
    if re.search(r'\b(?:report|dashboard|percent\w*|fraction|proportion|ratio|member|casual|classic|electric|e-bike|fleet|rider)\b|%', command, re.I):
        return None
    match = re.search(r'\bcompare\s+(?:the\s+)?(ride share for station|trip (?:counts?|starts) (?:at|for station))'
                      r'\s+([^\s,?!]+)(?=$|[,?!]|\s+(?:for|in|between|from|with|during|over)\b)', command, re.I)
    if match is None or not re.search(r'\d', match[2]):
        return None
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    names = '|'.join(month_name[1:])
    mentioned = set()
    month_pattern = r'\b(' + names + r')\b(?:\s+(\d{4}))?|\b(\d{4})-(\d{2})\b'
    suffix = command[match.end(2):]
    remaining = re.sub(month_pattern, ' ', suffix, flags=re.I)
    if any(word.casefold() not in {'for', 'the', 'month', 'months', 'in', 'between', 'from', 'with',
                                   'during', 'over', 'and', 'to', 'versus', 'vs', 'previous', 'prior', 'last'}
           for word in re.findall(r'\w+', remaining)):
        return None
    for item in re.finditer(month_pattern, suffix, re.I):
        if item[3]:
            mentioned.add((int(item[3]), int(item[4])))
        else:
            number = next(i for i, name in enumerate(month_name) if name.casefold() == item[1].casefold())
            inferred_year = previous[0] if number == previous[1] else year
            mentioned.add((int(item[2]) if item[2] else inferred_year, number))
    valid = mentioned == {(year, month), previous} or (
        not mentioned and bool(re.search(r'\b(?:previous|prior|last) month\b', command, re.I)))
    return {'kind': 'supported_ad_hoc', 'metric': 'station_starts', 'station_id': match[2],
            'comparison': True, 'unsupported_scope': not valid,
            'reason': ('Interpreted "ride share" as trip starts (counts), not a percentage.'
                       if match[1].casefold().startswith('ride') else None)}
